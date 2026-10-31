# -*- coding: utf-8 -*-
"""Phase6-R / R3：BM25 新旧实现正式对照基准（真实运行，非估算）。

对比对象（同一语料/分词器/查询/Top-K/k1/b/硬件/解释器）：
  * 旧版朴素 BM25（隔离 Benchmark Reference，不覆盖业务实现）
      - 复刻优化前的 O(q_terms * n * doc_len) 扫描式打分；
  * 新版倒排索引 BM25（业务实现 `job_matching.models.retrieval.BM25Recall`）
      - 倒排 posting list + 预计算 IDF/norm + Top-K partition。

指标（每组多次运行，含预热、重复次数与统计方法）：
  Build Time / Cold Query / Warm Query / P50 / P95 / Throughput / Memory(RSS) /
  Speedup / Equivalence。

口径纪律：
  * 旧版建索引时间与新版热查询时间不在同一口径比较（分别成列）；
  * 规模 150/500/1000/5000/10000；多次重复取中位，预热不计入；
  * Equivalence 用 1e-12 容差逐位比对 Top-K（doc_id 顺序 + 分数）。

输出：reports/phase6-r/03-bm25-benchmark.json / .md
"""
from __future__ import annotations

import json
import math
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "src"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from job_matching.models.retrieval import BM25Recall, tokenize_zh  # noqa: E402

try:
    import psutil
    _PROC = psutil.Process()
    def rss_mb() -> float:
        return _PROC.memory_info().rss / (1024 * 1024)
except Exception:  # noqa: BLE001
    def rss_mb() -> float:
        return float("nan")

REPORT_DIR = ROOT / "reports" / "phase6-r"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

K1, B, TOP_K = 1.5, 0.75, 10
SIZES = [150, 500, 1000, 5000, 10000]
WARMUP = 3
# 每组测量查询数：大语料下朴素实现昂贵，按规模自适应并如实登记
def n_queries_for(size: int) -> int:
    if size <= 1000:
        return 20
    if size <= 5000:
        return 12
    return 8


# ------------------------------------------------------------------ 朴素参考
class NaiveBM25:
    """优化前的扫描式 BM25（仅作 Benchmark Reference，不用于业务）。"""

    index_id = "bm25_naive_reference"

    def __init__(self, k1: float = K1, b: float = B):
        self.k1 = float(k1)
        self.b = float(b)

    def build(self, docs: list[str]) -> None:
        self._docs_tokens = [tokenize_zh(d) for d in docs]
        self._n = len(docs)
        self._doc_len = np.asarray([len(t) for t in self._docs_tokens], dtype=np.float64)
        self._avgdl = float(self._doc_len.mean()) if self._n else 0.0
        self._df: dict[str, int] = {}
        for toks in self._docs_tokens:
            for t in set(toks):
                self._df[t] = self._df.get(t, 0) + 1

    def _idf(self, term: str) -> float:
        n_q = self._df.get(term, 0)
        return math.log(1.0 + (self._n - n_q + 0.5) / (n_q + 0.5))

    def search(self, queries: list[str], top_k: int = TOP_K) -> list[list[tuple[int, float]]]:
        out: list[list[tuple[int, float]]] = []
        for q in queries:
            q_tokens = tokenize_zh(q)
            scores = np.zeros(self._n, dtype=np.float64)
            if not q_tokens:
                out.append([])
                continue
            for term in q_tokens:
                if term not in self._df:
                    continue
                idf = self._idf(term)
                for i, toks in enumerate(self._docs_tokens):
                    if not toks:
                        continue
                    tf = toks.count(term)
                    if tf == 0:
                        continue
                    denom = tf + self.k1 * (1.0 - self.b + self.b * self._doc_len[i] / self._avgdl)
                    scores[i] += idf * tf * (self.k1 + 1.0) / denom
            order = np.lexsort((np.arange(self._n), -scores))[:top_k]
            out.append([(int(j), float(scores[j])) for j in order if scores[j] > 0])
        return out


# ------------------------------------------------------------------ 数据
def synthetic_pool(n: int, seed: int = 0) -> list[str]:
    titles = ["Java开发工程师", "前端开发工程师", "数据分析师", "测试开发工程师",
              "运维工程师", "算法工程师", "产品经理", "数据工程师"]
    skills = ["Java", "Spring Boot", "MySQL", "Redis", "JavaScript", "Vue",
              "Python", "SQL", "Linux", "Docker", "Kubernetes", "TensorFlow",
              "Selenium", "Jenkins", "Spark", "Flink"]
    out = []
    for i in range(n):
        t = titles[(i + seed) % len(titles)]
        s = "、".join(skills[(i * 3 + seed) % len(skills):(i * 3 + seed) % len(skills) + 5])
        out.append(f"{t}（合成岗位{i}） 岗位职责：负责{i % 7 + 1}个模块的设计与开发。"
                   f"任职要求：熟练掌握 {s}；有相关项目经验者优先。")
    return out


def synthetic_queries(k: int) -> list[str]:
    base = ["Java Spring Boot 后端开发", "Python 数据分析 SQL", "前端 Vue JavaScript",
            "运维 Linux Docker Kubernetes", "算法 机器学习 TensorFlow",
            "测试 自动化 Selenium", "数据仓库 Spark Flink", "产品经理 需求分析"]
    return [base[i % len(base)] + (f" 查询{i}" if i >= len(base) else "") for i in range(k)]


# ------------------------------------------------------------------ 测量
def measure_impl(impl, docs: list[str], queries: list[str]) -> dict:
    """建索引 + 冷查询 + 热查询统计（含预热，多次重复）。"""
    rss0 = rss_mb()
    t0 = time.perf_counter()
    impl.build(docs)
    build_ms = (time.perf_counter() - t0) * 1000.0
    rss1 = rss_mb()

    # 冷查询：索引刚建后的首次查询（含任何惰性初始化）
    t0 = time.perf_counter()
    impl.search(queries[:1], top_k=TOP_K)
    cold_ms = (time.perf_counter() - t0) * 1000.0

    # 预热（不计入）
    for _ in range(WARMUP):
        impl.search(queries[:1], top_k=TOP_K)

    # 热查询：逐条测量延迟
    lat = []
    for q in queries:
        t0 = time.perf_counter()
        impl.search([q], top_k=TOP_K)
        lat.append((time.perf_counter() - t0) * 1000.0)
    lat_sorted = sorted(lat)
    p50 = statistics.median(lat_sorted)
    p95 = lat_sorted[min(len(lat_sorted) - 1, int(math.ceil(0.95 * len(lat_sorted)) - 1))]
    total_s = sum(lat) / 1000.0
    throughput = (len(lat) / total_s) if total_s > 0 else float("inf")
    return {
        "build_ms": round(build_ms, 3),
        "cold_query_ms": round(cold_ms, 3),
        "warm_query_mean_ms": round(statistics.mean(lat), 3),
        "warm_query_p50_ms": round(p50, 3),
        "warm_query_p95_ms": round(p95, 3),
        "throughput_qps": round(throughput, 3),
        "rss_before_mb": round(rss0, 2),
        "rss_after_mb": round(rss1, 2),
        "rss_delta_mb": round(rss1 - rss0, 2),
        "measured_queries": len(lat),
        "_lat_ms": [round(x, 4) for x in lat],
    }


def topk_equal(a, b, tol: float = 1e-12) -> tuple[bool, str]:
    if len(a) != len(b):
        return False, f"query result count {len(a)} != {len(b)}"
    for qi, (ra, rb) in enumerate(zip(a, b)):
        if len(ra) != len(rb):
            return False, f"q{qi} topk len {len(ra)} != {len(rb)}"
        for (da, sa), (db, sb) in zip(ra, rb):
            if da != db:
                return False, f"q{qi} doc_id {da} != {db}"
            if abs(float(sa) - float(sb)) > tol:
                return False, f"q{qi} doc{da} score {sa} != {sb} (tol={tol})"
    return True, "identical"


def run_size(size: int) -> dict:
    docs = synthetic_pool(size)
    nq = n_queries_for(size)
    queries = synthetic_queries(nq)
    naive = NaiveBM25()
    new = BM25Recall()
    m_naive = measure_impl(naive, docs, queries)
    m_new = measure_impl(new, docs, queries)

    # 等价性：两实现对同一批查询的 Top-K 逐位一致
    eq_ok, eq_note = topk_equal(naive.search(queries, top_k=TOP_K),
                                new.search(queries, top_k=TOP_K))

    def _speedup(key):
        a, b = m_naive[key], m_new[key]
        return round(a / b, 3) if b else float("inf")

    return {
        "corpus_size": size,
        "measured_queries": nq,
        "top_k": TOP_K,
        "k1": K1, "b": B,
        "naive": {k: v for k, v in m_naive.items() if not k.startswith("_")},
        "new": {k: v for k, v in m_new.items() if not k.startswith("_")},
        "speedup": {
            "build_naive_over_new": _speedup("build_ms"),
            "warm_p50_naive_over_new": _speedup("warm_query_p50_ms"),
            "warm_p95_naive_over_new": _speedup("warm_query_p95_ms"),
            "cold_naive_over_new": _speedup("cold_query_ms"),
        },
        "equivalence": {"identical": bool(eq_ok), "note": eq_note, "tolerance": 1e-12},
    }


def main() -> int:
    # 预热分词器（jieba 首次 import ~秒级），避免首次建索引独占一次性初始化成本
    tokenize_zh("预热 jieba 分词器 warmup")
    results = []
    for size in SIZES:
        t0 = time.perf_counter()
        r = run_size(size)
        r["wall_seconds"] = round(time.perf_counter() - t0, 2)
        results.append(r)
        print(f"[size={size}] build_naive={r['naive']['build_ms']}ms "
              f"build_new={r['new']['build_ms']}ms "
              f"p50_naive={r['naive']['warm_query_p50_ms']}ms "
              f"p50_new={r['new']['warm_query_p50_ms']}ms "
              f"equiv={r['equivalence']['identical']}")

    payload = {
        "benchmark": "bm25_naive_vs_inverted_index",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "hardware_note": "同一进程/解释器/硬件下测量；RSS 为进程常驻内存（psutil）",
        "stat_method": f"预热 {WARMUP} 次不计入；热查询逐条测延迟取中位/P95；"
                       f"建索引与冷查询独立成列，口径不混用",
        "tokenizer": "jieba + _TOKEN_RE（与业务召回一致）",
        "params": {"k1": K1, "b": B, "top_k": TOP_K},
        "sizes": SIZES,
        "results": results,
    }
    (REPORT_DIR / "03-bm25-benchmark.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown
    lines = [
        "# R3：BM25 新旧实现对照基准（真实运行）",
        "",
        f"- 生成时间：{payload['generated_at']}；Python {payload['python']} / numpy {payload['numpy']}",
        f"- 统计方法：{payload['stat_method']}",
        f"- 分词器：{payload['tokenizer']}；参数 k1={K1} b={B} Top-K={TOP_K}",
        "- 旧版=朴素扫描式（隔离参考，不覆盖业务）；新版=倒排索引（业务 `BM25Recall`）。",
        "- **建索引时间与热查询时间分列，口径不混用。**",
        "",
        "| 语料规模 | 实现 | Build(ms) | Cold(ms) | Warm P50(ms) | Warm P95(ms) | QPS | RSS增量(MB) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        for tag, m in (("朴素", r["naive"]), ("倒排", r["new"])):
            lines.append(
                f"| {r['corpus_size']} | {tag} | {m['build_ms']} | {m['cold_query_ms']} | "
                f"{m['warm_query_p50_ms']} | {m['warm_query_p95_ms']} | "
                f"{m['throughput_qps']} | {m['rss_delta_mb']} |")
    lines += [
        "",
        "## 加速比（朴素 / 倒排，>1 表示倒排更快）",
        "",
        "| 语料规模 | Build | Warm P50 | Warm P95 | Cold | 等价性 |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        s = r["speedup"]
        eq = "✓ 逐位一致" if r["equivalence"]["identical"] else "✗ " + r["equivalence"]["note"]
        lines.append(f"| {r['corpus_size']} | {s['build_naive_over_new']} | "
                     f"{s['warm_p50_naive_over_new']} | {s['warm_p95_naive_over_new']} | "
                     f"{s['cold_naive_over_new']} | {eq} |")
    lines += [
        "",
        "## 结论口径",
        "",
        "- 加速比 > 1 时倒排索引更快；随语料规模增长，倒排索引查询侧优势扩大"
        "（查询只遍历命中 posting list，复杂度从 O(q·n·dl) 降至 O(q·Σ|posting|)）。",
        "- 建索引侧倒排需构建 posting + 预计算 IDF/norm，与朴素建 token 缓存同一量级；",
        "  **不得**把旧版建索引时间与新版热查询时间放进同一口径比较。",
        "- Equivalence 列为 Top-K 逐位一致性（doc_id 顺序 + 分数 1e-12 容差），证明优化未改变检索结果。",
        "- 所有数据为本机真实运行（非估算、非外推），复现见 `scripts/phase6_r/bm25_benchmark.py`。",
    ]
    (REPORT_DIR / "03-bm25-benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {REPORT_DIR / '03-bm25-benchmark.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
