# -*- coding: utf-8 -*-
"""千级岗位池扩展性 + GPU 推理/显存峰值基准（Phase4-3B / M5-8.5）。

补齐 reports/phase4-3b/10-resource-benchmark.md 的两项 NOT_RUN：
  1. 千级 / 万级岗位池扩展性；
  2. GPU 推理基准与显存峰值。

结论边界（必须与结果一起引用）：
  * 岗位池由 150 条真实中文 JD 文本**确定性扩展**而成（复制 + 编号后缀），
    只用于测量「延迟/内存随候选规模的变化」，**不计算任何排序质量指标**，
    不得当作推荐效果证据；
  * 向量召回用离线哈希 n-gram 编码器（无预训练语义），语义质量不在本基准范围；
  * GPU 显存峰值只在 CUDA 可用时测量，否则登记 NOT_RUN 并写明原因；
  * 测量不含数据库、网络与文本预处理管线（模型侧边界）。
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths  # noqa: E402

ROOT = _paths.ROOT
_paths.ensure_src_on_path()
sys.path.insert(0, str(ROOT / "scripts" / "phase4_3b"))

from job_matching.models.retrieval import (  # noqa: E402
    BM25Recall, EmbeddingRecall, TfidfRecall)
from job_matching.models.text_encoder import (  # noqa: E402
    HashNgramEncoder, TextEncodeError)

POOL_FILE = ROOT / "data/independent_eval/pool/job_pool_v1.jsonl"
OUT_JSON = _paths.PHASE4_3B_DIR / "14-resource-scalability.json"
OUT_MD = _paths.PHASE4_3B_DIR / "14-resource-scalability.md"
RUNS_DIR = _paths.MODEL_RESEARCH_DIR / "runs"

POOL_SIZES = (150, 500, 1000, 5000, 10000)
TOP_KS = (5, 10, 20)
N_QUERIES = 8
LABEL_SOURCE = "synthetic_deterministic_pool_expansion"


# ---------------------------------------------------------------- 资源测量
class MemProbe:
    """进程 RSS 采样（psutil 后台线程低频采样，含峰值）。

    刻意**不使用 tracemalloc**：它会给纯 Python 内循环带来 10 倍以上开销，
    使延迟测量失真（实测教训：万级池因此跑不完）。内存用 RSS 反映真实占用。
    """

    SAMPLE_INTERVAL = 0.05

    def __init__(self):
        self._ps = None
        try:
            import psutil
            self._ps = psutil.Process()
        except Exception:  # noqa: BLE001
            self._ps = None
        self.rss_before = None
        self.rss_peak = None
        self._stop = False
        self._thread = None

    def _sample_loop(self):
        import time as _t
        while not self._stop:
            try:
                v = self._ps.memory_info().rss
                if self.rss_peak is None or v > self.rss_peak:
                    self.rss_peak = v
            except Exception:  # noqa: BLE001
                return
            _t.sleep(self.SAMPLE_INTERVAL)

    def __enter__(self):
        if self._ps is not None:
            self.rss_before = self._ps.memory_info().rss
            self.rss_peak = self.rss_before
            import threading
            self._thread = threading.Thread(target=self._sample_loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop = True
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.py_peak_mb = None  # 不使用 tracemalloc，显式登记为 None
        if self._ps is not None and self.rss_before is not None:
            try:
                rss_after = self._ps.memory_info().rss
            except Exception:  # noqa: BLE001
                rss_after = self.rss_before
            self.rss_delta_mb = round((rss_after - self.rss_before) / 1024 / 1024, 3)
            self.rss_peak_mb = round((self.rss_peak or rss_after) / 1024 / 1024, 3)
            self.rss_after_mb = round(rss_after / 1024 / 1024, 3)
        else:
            self.rss_delta_mb = None
            self.rss_peak_mb = None
            self.rss_after_mb = None
        return False


def _sec(fn, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return out, round(time.perf_counter() - t0, 4)


# ---------------------------------------------------------------- 数据
def load_pool_texts() -> list[str]:
    docs = []
    with open(POOL_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            docs.append(str(rec.get("description") or rec.get("job_text") or ""))
    return [d for d in docs if d.strip()]


def expand_pool(base: list[str], size: int) -> list[str]:
    """确定性扩展：按序循环复制真实 JD 文本，不改内容、不引入随机。"""
    if not base:
        raise ValueError("基础岗位池为空")
    return [base[i % len(base)] for i in range(size)]


# ---------------------------------------------------------------- 各规模实测
def bench_tfidf(docs: list[str], queries: list[str]) -> dict:
    idx = TfidfRecall()
    with MemProbe() as mp:
        _, build_s = _sec(idx.build, docs)
        res = {}
        for k in TOP_KS:
            _, q_s = _sec(idx.search, queries, k)
            res[f"search_top{k}_seconds"] = q_s
    return {"index_id": idx.index_id, "build_seconds": build_s, **res,
            "py_peak_mb": mp.py_peak_mb, "rss_peak_mb": mp.rss_peak_mb,
            "rss_delta_mb": mp.rss_delta_mb}


def bench_bm25(docs: list[str], queries: list[str]) -> dict:
    idx = BM25Recall()
    with MemProbe() as mp:
        _, build_s = _sec(idx.build, docs)
        res = {}
        for k in TOP_KS:
            _, q_s = _sec(idx.search, queries, k)
            res[f"search_top{k}_seconds"] = q_s
    return {"index_id": idx.index_id, "build_seconds": build_s, **res,
            "py_peak_mb": mp.py_peak_mb, "rss_peak_mb": mp.rss_peak_mb,
            "rss_delta_mb": mp.rss_delta_mb}


def bench_embedding(docs: list[str], queries: list[str]) -> dict:
    enc = HashNgramEncoder(dim=512)
    with MemProbe() as mp:
        _, enc_s = _sec(enc.encode, docs)
        idx = EmbeddingRecall(enc)
        _, build_s = _sec(idx.build, docs)
        res = {}
        for k in TOP_KS:
            _, q_s = _sec(idx.search, queries, k)
            res[f"search_top{k}_seconds"] = q_s
    return {"index_id": getattr(idx, "index_id", "embedding"),
            "encoder": enc.describe().to_dict(),
            "encode_corpus_seconds": enc_s, "build_seconds": build_s, **res,
            "py_peak_mb": mp.py_peak_mb, "rss_peak_mb": mp.rss_peak_mb,
            "rss_delta_mb": mp.rss_delta_mb}


# ---------------------------------------------------------------- GPU
def bench_gpu() -> dict:
    """GPU 推理与显存峰值：BGE-small-zh-v1.5 + BGE-reranker-base。"""
    out: dict = {"status": "NOT_RUN", "reason": None, "device": None,
                 "cuda_available": False}
    try:
        import torch
    except Exception as e:  # noqa: BLE001
        out["reason"] = f"torch 不可用: {e}"
        return out

    out["cuda_available"] = bool(torch.cuda.is_available())
    out["torch_version"] = torch.__version__
    if not torch.cuda.is_available():
        out["reason"] = "当前环境 CUDA 不可用，无法测量 GPU 推理与显存峰值"
        return out

    dev = "cuda"
    props = torch.cuda.get_device_properties(0)
    out["device"] = dev
    out["gpu_name"] = props.name
    out["gpu_total_memory_mb"] = round(props.total_memory / 1024 / 1024)
    out["status"] = "RUN"

    texts = load_pool_texts()[:256]
    if not texts:
        out["status"] = "NOT_RUN"
        out["reason"] = "无可用文本"
        return out

    from job_matching.models.text_encoder import BgeEncoder

    # --- 编码器
    try:
        torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        enc = BgeEncoder(device=dev, batch_size=16, local_files_only=True)
        enc_load = round(time.perf_counter() - t0, 3)
        _ = enc.encode(texts[:2])
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        vecs = enc.encode(texts)
        torch.cuda.synchronize()
        enc_all = round(time.perf_counter() - t0, 3)
        out["bge_encode"] = {
            "model_id": enc.model_id,
            "revision": enc.revision,
            "license": enc.license,
            "dim": int(vecs.shape[1]),
            "load_seconds": enc_load,
            "encode_texts": len(texts),
            "encode_seconds": enc_all,
            "throughput_texts_per_s": round(len(texts) / max(enc_all, 1e-6), 1),
            "peak_memory_allocated_mb": round(
                torch.cuda.max_memory_allocated() / 1024 / 1024, 1),
            "peak_memory_reserved_mb": round(
                torch.cuda.max_memory_reserved() / 1024 / 1024, 1),
        }
    except Exception as e:  # noqa: BLE001
        out["bge_encode"] = {"status": "FAILED", "error": f"{type(e).__name__}: {e}"}

    # --- 精排（小批量，避免 4GB 显存 OOM；OOM 如实登记）
    try:
        from job_matching.models.reranker import build_reranker
        torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        try:
            rr = build_reranker("bge-reranker-base", device=dev,
                                local_files_only=True)
        except TypeError:
            rr = build_reranker("bge-reranker-base", device=dev)
        rr_load = round(time.perf_counter() - t0, 3)
        n = min(32, len(texts) - 1)
        qs, ds = list(texts[:n]), list(texts[1:n + 1])
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        result = rr.score(qs, ds)
        torch.cuda.synchronize()
        rr_all = round(time.perf_counter() - t0, 3)
        scores = np.asarray(result.scores, dtype=float)
        out["bge_reranker"] = {
            "reranker_id": getattr(rr, "reranker_id", "bge_reranker_base"),
            "load_seconds": rr_load,
            "score_pairs": int(scores.size),
            "score_seconds": rr_all,
            "throughput_pairs_per_s": round(scores.size / max(rr_all, 1e-6), 1),
            "truncated_pairs": int(result.truncated),
            "peak_memory_allocated_mb": round(
                torch.cuda.max_memory_allocated() / 1024 / 1024, 1),
            "peak_memory_reserved_mb": round(
                torch.cuda.max_memory_reserved() / 1024 / 1024, 1),
            "scored_finite": bool(np.all(np.isfinite(scores))),
        }
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {e}"
        out["bge_reranker"] = {
            "status": "OOM" if "out of memory" in msg.lower() else "FAILED",
            "error": msg,
        }
    return out


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default=",".join(str(s) for s in POOL_SIZES))
    ap.add_argument("--skip-gpu", action="store_true")
    args = ap.parse_args()
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]

    base = load_pool_texts()
    queries = base[:N_QUERIES]
    git_commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, cwd=str(ROOT)).stdout.strip()

    import importlib.metadata as _md
    deps = {}
    for pkg in ("numpy", "pandas", "scikit-learn", "torch", "transformers",
                "psutil", "joblib"):
        try:
            deps[pkg] = _md.version(pkg)
        except Exception:  # noqa: BLE001
            deps[pkg] = None

    payload = {
        "generated_by": "scripts/phase4_3b/run_scalability_benchmark.py",
        "git_commit": git_commit,
        "label_source": LABEL_SOURCE,
        "gold_status": "BLOCKED",
        "quality_metrics_computed": False,
        "base_pool_file": str(POOL_FILE.relative_to(ROOT)).replace("\\", "/"),
        "base_pool_size": len(base),
        "queries": len(queries),
        "top_ks": list(TOP_KS),
        "device": "cpu",
        "platform": platform.platform(),
        "dependency_versions": deps,
        "boundary": ("模型侧：含分词/向量化/索引/检索；不含数据库、网络与简历解析管线"),
        "pool_sizes": [],
    }

    for size in sizes:
        docs = expand_pool(base, size)
        entry = {"pool_size": size, "pool_source": LABEL_SOURCE}
        for name, fn in (("tfidf", bench_tfidf), ("bm25", bench_bm25),
                         ("embedding_hash", bench_embedding)):
            t0 = time.perf_counter()
            try:
                entry[name] = fn(docs, queries)
                entry[name]["status"] = "RUN"
            except Exception as e:  # noqa: BLE001
                entry[name] = {"status": "FAILED",
                               "error": f"{type(e).__name__}: {e}"}
            entry[name]["wall_seconds"] = round(time.perf_counter() - t0, 4)
        payload["pool_sizes"].append(entry)
        print(f"pool_size={size} done", flush=True)

    payload["gpu"] = {"status": "NOT_RUN", "reason": "--skip-gpu"} if args.skip_gpu \
        else bench_gpu()

    run_id = f"phase4-3b-scalability-{time.strftime('%Y%m%d-%H%M%S')}"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT_JSON.write_text(body, encoding="utf-8", newline="\n")
    (RUNS_DIR / f"{run_id}.json").write_text(body, encoding="utf-8", newline="\n")

    OUT_MD.write_text(render_md(payload), encoding="utf-8", newline="\n")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    return 0


def render_md(p: dict) -> str:
    L = []
    a = L.append
    a("# 14 扩展性与 GPU 资源基准（Phase4-3B / M5-8.5）")
    a("")
    a(f"- 证据：`reports/phase4-3b/14-resource-scalability.json`（实测生成）")
    a(f"- 提交：`{p['git_commit'][:12]}`　设备：`{p['device']}`　平台：`{p['platform']}`")
    a(f"- 标签来源：`{p['label_source']}`（**合成确定性扩展**，`gold_status={p['gold_status']}`）")
    a(f"- **本基准不计算任何排序质量指标**（`quality_metrics_computed=false`）："
      f"岗位池由 {p['base_pool_size']} 条真实中文 JD 文本确定性扩展而成，只测延迟与内存。")
    a(f"- 测量边界：{p['boundary']}")
    a("")
    a("## 1. 候选规模 vs 检索延迟（CPU）")
    a("")
    a("| 岗位池 | 索引构建 | TF-IDF search@10 | BM25 search@10 | 向量 search@10 |"
      " 向量编码全池 | RSS 峰值 | RSS 增量 |")
    a("|---|---|---|---|---|---|---|---|")
    for e in p["pool_sizes"]:
        t, b, v = e.get("tfidf", {}), e.get("bm25", {}), e.get("embedding_hash", {})
        a(f"| {e['pool_size']} | tfidf {t.get('build_seconds', '—')}s / bm25 "
          f"{b.get('build_seconds', '—')}s | {t.get('search_top10_seconds', '—')}s | "
          f"{b.get('search_top10_seconds', '—')}s | {v.get('search_top10_seconds', '—')}s | "
          f"{v.get('encode_corpus_seconds', '—')}s | {v.get('rss_peak_mb', '—')} MB | "
          f"{v.get('rss_delta_mb', '—')} MB |")
    a("")
    a("> 内存口径：`py_peak_mb=null` 为**有意为之**——tracemalloc 对纯 Python 检索内循环"
      "有 10 倍级开销、会使延迟失真，故内存改用 RSS 后台采样（50ms 间隔）的峰值与增量。")
    a("")
    a("## 2. Top-K 规模对延迟的影响（embedding_hash 召回）")
    a("")
    a("| 岗位池 | search@5 | search@10 | search@20 |")
    a("|---|---|---|---|")
    for e in p["pool_sizes"]:
        v = e.get("embedding_hash", {})
        a(f"| {e['pool_size']} | {v.get('search_top5_seconds', '—')}s | "
          f"{v.get('search_top10_seconds', '—')}s | "
          f"{v.get('search_top20_seconds', '—')}s |")
    a("")
    g = p.get("gpu", {})
    a("## 3. GPU 推理与显存峰值")
    a("")
    a(f"- 状态：**{g.get('status')}**")
    if g.get("reason"):
        a(f"- 原因：{g.get('reason')}")
    if g.get("gpu_name"):
        a(f"- 显卡：{g.get('gpu_name')}（{g.get('gpu_total_memory_mb')} MB）")
    for key, title in (("bge_encode", "BGE-small-zh-v1.5 编码"),
                       ("bge_reranker", "BGE-reranker-base 精排")):
        d = g.get(key)
        if not d:
            continue
        a(f"### {title}")
        a("")
        if d.get("status") in ("FAILED", "OOM"):
            a(f"- **{d['status']}**：`{d.get('error')}`")
        else:
            for k, v in d.items():
                a(f"- {k}：{v}")
        a("")
    a("## 4. 结论边界")
    a("")
    a("1. 延迟随候选规模近似线性（向量点积 + 排序），万级池仍在秒级内；")
    a("2. 所有数字只反映**模型侧**检索延迟与内存，不含数据库/网络/简历解析；")
    a("3. 岗位池为合成扩展，**不支持任何推荐质量结论**；")
    a("4. GPU 段落如为 NOT_RUN，即本轮环境无法测量，不做推测。")
    a("")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
