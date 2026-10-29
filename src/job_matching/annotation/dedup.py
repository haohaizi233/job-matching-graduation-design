# -*- coding: utf-8 -*-
"""文本重复与近似重复检测（协议 3.4 / 泄漏检查）。

三级口径（严格区分，报告不得混称）：
  1. 完全重复      : 规范化文本 SHA-256 完全相同（norm_text 口径）
  2. 规范化文本重复: 强规范化（NFKC + 小写 + 去空白 + 去标点）后 SHA-256 相同
  3. 近似重复      : 字符 n-gram shingle Jaccard >= threshold（默认 0.90）

近似重复使用 shingle 倒排索引做候选阻塞（blocking）后再算精确 Jaccard，
可扩展到十万级语料；阻塞可能漏检极端情况，报告中如实登记该限制。
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import defaultdict

_PUNCT = re.compile(r"[\s\W_]+", re.UNICODE)

DEFAULT_NEAR_THRESHOLD = 0.90
DEFAULT_SHINGLE_N = 3
_BLOCK_MIN_SHARED = 3
_BLOCK_MAX_DF = 400


def norm_text_basic(s) -> str:
    """完全重复口径：NFKC + 空白折叠 + 去首尾空白（与 core.norm_text 一致）。"""
    if s is None:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = re.sub(r"\s+", " ", t).strip()
    return t


def norm_text_strong(s) -> str:
    """规范化文本重复口径：NFKC + 小写 + 去空白与标点。"""
    t = norm_text_basic(s).lower()
    return _PUNCT.sub("", t)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hash_shingles(sh: set[str]) -> set[int]:
    """shingle 串 -> 稳定 32 位整数（跨进程一致，降低倒排索引内存）。"""
    out = set()
    for s in sh:
        out.add(int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=4).digest(), "big"))
    return out


def exact_hash(s) -> str:
    return sha256_text(norm_text_basic(s))


def norm_hash(s) -> str:
    return sha256_text(norm_text_strong(s))


def shingles(s, n: int = DEFAULT_SHINGLE_N) -> set[str]:
    t = norm_text_strong(s)
    if not t:
        return set()
    if len(t) <= n:
        return {t}
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / float(len(a) + len(b) - inter)


def near_duplicate_pairs(texts: dict[str, str], threshold: float = DEFAULT_NEAR_THRESHOLD,
                         n: int = DEFAULT_SHINGLE_N) -> list[dict]:
    """返回近似重复对 [{a, b, similarity}]（a < b，按字典序，结果确定）。

    texts: {doc_id: text}。空文本不参与。
    """
    docs = {k: shingles(v, n) for k, v in texts.items()}
    docs = {k: v for k, v in docs.items() if v}
    # 倒排索引阻塞
    inv: dict[str, list[str]] = defaultdict(list)
    for k in sorted(docs):
        for sh in docs[k]:
            inv[sh].append(k)
    shared: dict[tuple[str, str], int] = defaultdict(int)
    for sh, ids in inv.items():
        if len(ids) < 2 or len(ids) > _BLOCK_MAX_DF:
            continue
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                shared[(ids[i], ids[j])] += 1
    out: list[dict] = []
    min_len = {k: len(v) for k, v in docs.items()}
    for (a, b), cnt in sorted(shared.items()):
        # Jaccard 上界 = shared / min(|A|,|B|)，不达阈值直接跳过
        if cnt < _BLOCK_MIN_SHARED:
            continue
        if cnt / float(max(1, min(min_len[a], min_len[b]))) < threshold:
            continue
        sim = jaccard(docs[a], docs[b])
        if sim >= threshold:
            out.append({"a": a, "b": b, "similarity": round(float(sim), 6)})
    return out


def cross_near_duplicate_pairs(target: dict[str, str], reference,
                               threshold: float = DEFAULT_NEAR_THRESHOLD,
                               n: int = DEFAULT_SHINGLE_N,
                               max_df: int = _BLOCK_MAX_DF) -> list[dict]:
    """目标集合 vs 参考集合的跨集合近似重复（训练/评估泄漏检查）。

    reference 可以是 {key: text} 或可迭代的 (key, text)（大语料逐条流式扫描，
    不一次性建全量倒排索引，控制内存）。阻塞方式：以目标集合的 shingle 建索引，
    流式扫描参考语料做候选计数，再算精确 Jaccard。
    """
    ref_iter = reference.items() if isinstance(reference, dict) else reference
    t_docs = {k: shingles(v, n) for k, v in target.items()}
    t_docs = {k: v for k, v in t_docs.items() if v}
    if not t_docs:
        return []
    t_index: dict[str, list[str]] = defaultdict(list)
    t_len: dict[str, int] = {}
    for k in sorted(t_docs):
        t_len[k] = len(t_docs[k])
        for sh in t_docs[k]:
            t_index[sh].append(k)

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rkey, rtext in ref_iter:
        rsh = shingles(rtext, n)
        if not rsh:
            continue
        counts: dict[str, int] = defaultdict(int)
        for sh in rsh:
            for tkey in t_index.get(sh, ()):
                counts[tkey] += 1
        for tkey in sorted(counts):
            cnt = counts[tkey]
            if cnt < _BLOCK_MIN_SHARED:
                continue
            if cnt / float(max(1, min(t_len[tkey], len(rsh)))) < threshold:
                continue
            sim = jaccard(t_docs[tkey], rsh)
            if sim >= threshold:
                key = (tkey, str(rkey))
                if key not in seen:
                    seen.add(key)
                    out.append({"a": tkey, "b": str(rkey), "similarity": round(float(sim), 6)})
    return out


class DuplicateIndex:
    """顺序插入式去重索引：新文本与已登记文本做完全/规范化/近似重复判定。

    check_near=False 时只做完全 + 规范化哈希去重（用于十万级语料的快速预筛）；
    近似重复阻塞以「已登记文本的 shingle 倒排」做候选查找，只对候选算精确 Jaccard。
    """

    def __init__(self, threshold: float = DEFAULT_NEAR_THRESHOLD,
                 n: int = DEFAULT_SHINGLE_N, check_near: bool = True):
        self.threshold = float(threshold)
        self.n = int(n)
        self.check_near = bool(check_near)
        self._exact: dict[str, str] = {}
        self._norm: dict[str, str] = {}
        self._items: dict[str, set[str]] = {}
        self._inv: dict[int, list[str]] = defaultdict(list)
        self._texts: dict[str, str] = {}

    def check(self, key: str, text: str) -> dict:
        """返回 {status, dup_of, similarity}。status: unique|exact_dup|norm_dup|near_dup。"""
        eh = exact_hash(text)
        if eh in self._exact:
            return {"status": "exact_dup", "dup_of": self._exact[eh], "similarity": 1.0}
        nh = norm_hash(text)
        if nh in self._norm:
            return {"status": "norm_dup", "dup_of": self._norm[nh], "similarity": 1.0}
        sh = shingles(text, self.n)
        hashed = _hash_shingles(sh)
        best: tuple[str, float] | None = None
        if self.check_near and hashed:
            shared: dict[str, int] = defaultdict(int)
            for hsh in hashed:
                for other in self._inv.get(hsh, ()):
                    shared[other] += 1
            for other in sorted(shared):
                if shared[other] < _BLOCK_MIN_SHARED:
                    continue
                sim = jaccard(sh, self._items[other])
                if sim >= self.threshold and (best is None or sim > best[1]):
                    best = (other, sim)
        if best is not None:
            return {"status": "near_dup", "dup_of": best[0], "similarity": round(best[1], 6)}
        self._exact[eh] = key
        self._norm[nh] = key
        self._items[key] = sh
        for hsh in hashed:
            self._inv[hsh].append(key)
        self._texts[key] = text
        return {"status": "unique", "dup_of": None, "similarity": 0.0}

    def add(self, key: str, text: str) -> dict:
        return self.check(key, text)

    def __len__(self) -> int:
        return len(self._items)


def min_shared_for_threshold(threshold: float, n_docs_shingle_min: int) -> int:
    """阻塞候选所需的最小共享 shingle 数（供报告记录口径）。"""
    return max(_BLOCK_MIN_SHARED, int(math.ceil(threshold * max(1, n_docs_shingle_min))))
