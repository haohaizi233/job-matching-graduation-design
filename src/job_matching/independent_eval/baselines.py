# -*- coding: utf-8 -*-
"""独立评估基线与模型适用性登记（协议第八节 / 测试场景 14）。

原则：
  * 可执行的基线必须从 pair 的原始字段独立计算，不读取任何旧系统派生分数；
  * 不能直接用于真实 JD 评估的方法必须显式登记原因并抛出显式错误，
    绝不为了参加对比而制造不可获得的线上输入；
  * 已归档模型（Ridge/GBDT/MLP/RankNet）只做前向推理，绝不重新训练。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..core import ROOT
from .metrics import HUMAN_GAIN  # noqa: F401  (保持口径同源)


class ModelUnavailableError(RuntimeError):
    """模型/基线不可用：必须显式报错，不得静默跳过或伪造分数。"""


# ------------------------------------------------------------------ 适用性登记
APPLICABILITY = {
    "keyword_skill": {
        "applicable": True,
        "needs": ["resume_skills", "required_skills"],
        "note": "技能重合基线，从 pair 原始字段直接计算",
    },
    "tfidf_cosine": {
        "applicable": True,
        "needs": ["resume_text", "job_text"],
        "note": "字符 n-gram TF-IDF 余弦；IDF 在评估池文本上拟合（无监督，不接触标签）",
    },
    "embedding_cosine": {
        "applicable": False,
        "needs": ["embedding(resume)", "embedding(job)"],
        "note": ("预计算 embedding 仅覆盖英文 job-resume-matching 数据集，"
                 "编码器未知（docs/evaluation-protocol.md 第〇节第 4 条）；"
                 "无法为真实中文 pair 生成同源 embedding"),
    },
    "ridge": {"applicable": "conditional", "needs": ["MatchPredictor 白名单原始字段"],
              "note": "训练标签为英文代理标签、技能规范化词表为英文；结果只作参考"},
    "gradient_boosting": {"applicable": "conditional", "needs": ["同上"],
                          "note": "同 ridge"},
    "mlp": {"applicable": "conditional", "needs": ["同上"], "note": "同 ridge"},
    "ranknet": {"applicable": "conditional", "needs": ["同上"], "note": "同 ridge"},
}

TRAINED_MODELS = ("ridge", "gradient_boosting", "mlp", "ranknet")


# ------------------------------------------------------------------ 基线打分
def _json_set(value) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(v).strip().lower() for v in value if str(v).strip()}
    s = str(value).strip()
    if not s:
        return set()
    if s.startswith("["):
        try:
            return {str(v).strip().lower() for v in json.loads(s) if str(v).strip()}
        except Exception:
            return set()
    return {p.strip().lower() for p in s.replace("；", ";").replace("、", ";").split(";") if p.strip()}


def keyword_skill_scores(pairs: list[dict]) -> np.ndarray:
    out = []
    for p in pairs:
        r = _json_set(p.get("resume_skills"))
        j = _json_set(p.get("required_skills"))
        if not r and not j:
            out.append(0.0)
            continue
        inter = len(r & j)
        out.append(inter / float(len(r | j)))
    return np.asarray(out, dtype=np.float64)


def tfidf_cosine_scores(pairs: list[dict], ngram_max: int = 4) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    if not pairs:
        return np.zeros(0, dtype=np.float64)
    resumes = [str(p.get("resume_text") or "") for p in pairs]
    jobs = [str(p.get("job_text") or "") for p in pairs]
    if not any(resumes) or not any(jobs):
        raise ValueError("TF-IDF 基线需要非空的 resume_text 与 job_text（不允许在全空文本上拟合 IDF）")
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, int(ngram_max)),
                          min_df=1, sublinear_tf=True)
    X = vec.fit_transform(resumes + jobs)
    Xr, Xj = X[:len(pairs)], X[len(pairs):]
    # 对角线 = 每个 (resume, job) 配对自身的余弦相似度
    sims = cosine_similarity(Xr, Xj, dense_output=False).diagonal()
    return np.asarray(sims, dtype=np.float64).ravel()


def features_from_pair(pair: dict) -> tuple[dict, dict]:
    """pair 原始字段 -> MatchPredictor 输入（白名单字段，不接触派生分数）。"""
    from ..domain.job_rules import classify_job_category
    years = pair.get("resume_years_experience")
    try:
        years_v = float(years) if str(years).strip() != "" else float("nan")
    except (TypeError, ValueError):
        years_v = float("nan")
    resume = {
        "target_position_norm": str(pair.get("resume_target_position") or ""),
        "skills_canonical_json": str(pair.get("resume_skills") or "[]"),
        "inferred_category": classify_job_category(
            pair.get("resume_target_position", ""))[0],
        "years_experience": years_v,
    }
    job = {
        "job_title_norm": str(pair.get("job_title") or ""),
        "category": str(pair.get("job_category") or ""),
        "skills_canonical_json": str(pair.get("required_skills") or "[]"),
    }
    return resume, job


def resolve_run_dir(model_name: str, protocol: str = "candidate_cold") -> Path | None:
    """定位已归档模型目录（确定性：排除 smoke/ablation，取名称排序最后）。"""
    base = ROOT / "models" / "matching" / model_name
    if not base.exists():
        return None
    cands = []
    for run in sorted(base.glob(f"{protocol}/*")):
        if not (run / "manifest.json").exists():
            continue
        low = run.name.lower()
        if "smoke" in low or "ablation" in low:
            continue
        cands.append(run)
    return cands[-1] if cands else None


def trained_model_scores(model_name: str, pairs: list[dict],
                         run_dir: Path | str | None = None) -> np.ndarray:
    if model_name not in TRAINED_MODELS:
        raise ModelUnavailableError(f"未登记的模型: {model_name}")
    rd = Path(run_dir) if run_dir else resolve_run_dir(model_name)
    if rd is None or not rd.exists():
        raise ModelUnavailableError(
            f"模型 {model_name!r} 的归档目录不存在（models/matching/{model_name}），"
            "禁止用占位分数代替")
    try:
        from ..inference.predictor import MatchPredictor
        pred = MatchPredictor(rd, device="cpu")
    except Exception as e:  # 加载失败必须显式报错
        raise ModelUnavailableError(f"模型 {model_name!r} 加载失败: {e}") from e
    out = []
    for p in pairs:
        resume, job = features_from_pair(p)
        out.append(float(pred.predict_score(resume, job)))
    return np.asarray(out, dtype=np.float64)


def score_with(name: str, pairs: list[dict], **kw) -> np.ndarray:
    """统一打分入口：不可用的方法抛 ModelUnavailableError（显式错误）。"""
    if name == "keyword_skill":
        return keyword_skill_scores(pairs)
    if name == "tfidf_cosine":
        return tfidf_cosine_scores(pairs)
    if name == "embedding_cosine":
        raise ModelUnavailableError(
            f"embedding_cosine 不适用于真实中文评估集：{APPLICABILITY['embedding_cosine']['note']}")
    if name in TRAINED_MODELS:
        return trained_model_scores(name, pairs, run_dir=kw.get("run_dir"))
    raise ModelUnavailableError(f"未登记的基线/模型: {name}")


def applicability_report() -> dict:
    models = {}
    for name in list(APPLICABILITY):
        entry = dict(APPLICABILITY[name])
        if name in TRAINED_MODELS:
            rd = resolve_run_dir(name)
            entry["archived_run_dir"] = str(rd) if rd else None
            entry["loadable"] = bool(rd and rd.exists())
            entry["usable_for_formal_chinese_gold"] = False
        else:
            entry["usable_for_formal_chinese_gold"] = bool(entry.get("applicable") is True)
        models[name] = entry
    return {
        "models": models,
        "policy": ("不允许为了让某个模型参加对比而制造不可获得的线上输入；"
                   "特征无法从真实 pair 原始字段重建的方法登记为 applicable=false 并显式报错"),
        "caveat": ("已归档模型的训练标签是英文代理标签（docs/evaluation-protocol.md 第〇节），"
                   "其在中文人工 Gold 上的分数只能作参考，不得作为中文真实适配结论"),
    }
