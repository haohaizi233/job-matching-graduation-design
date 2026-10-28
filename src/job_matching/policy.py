# -*- coding: utf-8 -*-
"""特征白名单 / 黑名单执行与目标泄漏防护（第三阶段 3.1.2，验收项 P3-03）。

三类检查：
  A. 静态检查  —— 特征列名不得命中黑名单 / ID 列 / 目标列
  B. 动态检查  —— 实际构建出的 DataFrame / Tensor 特征矩阵逐列核对
  C. 间接泄漏  —— 特征不得近乎确定地重建任何禁止字段（final_score 等）
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import get_config


class LeakageError(RuntimeError):
    """发现目标泄漏，必须立即终止后续流程。"""


@dataclass
class PolicyCheckResult:
    task: str
    ok: bool
    checked_columns: list[str]
    violations: list[dict]
    indirect_findings: list[dict]

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "ok": self.ok,
            "checked_columns": self.checked_columns,
            "violations": self.violations,
            "indirect_findings": self.indirect_findings,
        }


def _as_list(x) -> list[str]:
    return [str(v) for v in (x or [])]


def forbidden_for_task(task: str) -> set[str]:
    cfg = get_config()
    t = cfg.task(task)
    out = set(cfg.always_forbidden())
    out.update(_as_list(t.get("forbidden_features")))
    out.update(_as_list(t.get("target_columns")))
    out.update(_as_list(t.get("target_derived_columns")))
    out.update(_as_list(t.get("relevance_columns")))
    return out


def allowed_for_task(task: str) -> set[str]:
    cfg = get_config()
    return set(_as_list(cfg.task(task).get("allowed_features")))


def uncertain_for_task(task: str) -> set[str]:
    cfg = get_config()
    return set(_as_list(cfg.task(task).get("uncertain_features")))


def evaluation_metadata_for_task(task: str) -> set[str]:
    cfg = get_config()
    return set(_as_list(cfg.task(task).get("evaluation_metadata")))


def strip_side_prefix(name: str) -> str:
    """pair.skill_jaccard -> skill_jaccard；cv.x -> x。用于列名比对。"""
    return name.split(".", 1)[1] if "." in name else name


# ------------------------------------------------------------------ A/B 静态+动态
def check_feature_columns(task: str, columns: list[str],
                          raise_on_violation: bool = True,
                          allow_uncertain: bool = False) -> PolicyCheckResult:
    """核对实际特征列（DataFrame 列名或特征矩阵列名）是否符合任务策略。

    allow_uncertain=False（默认）：uncertain_features（待定/有泄漏风险）视同违规，
    必须由调用方显式声明 allow_uncertain=True 才能放行，且报告中必须标注风险。
    """
    cfg = get_config()
    t = cfg.task(task)
    cols = [str(c) for c in columns]

    forbidden = forbidden_for_task(task)
    id_like = set(cfg.id_like_columns())
    allowed = allowed_for_task(task)
    allowed_flat = {strip_side_prefix(a) for a in allowed}
    uncertain = uncertain_for_task(task)
    uncertain_flat = {strip_side_prefix(u) for u in uncertain}

    violations: list[dict] = []
    for c in cols:
        base = strip_side_prefix(c)
        if c in forbidden or base in forbidden:
            violations.append({"column": c, "reason": "命中任务黑名单 / 目标列"})
        elif c in id_like or base in id_like:
            violations.append({"column": c, "reason": "ID 类列禁止作为语义特征"})
        elif base in uncertain_flat:
            violations.append({"column": c, "reason": "属于待定/有泄漏风险特征",
                               "severity": "warn" if allow_uncertain else "hard"})
        elif base not in allowed_flat:
            violations.append({"column": c, "reason": "不在任务白名单内"})

    # 目标列与特征列不得有交集（物理隔离）
    for tc in _as_list(t.get("target_columns")) + _as_list(t.get("target_derived_columns")):
        for c in cols:
            if strip_side_prefix(c) == tc:
                violations.append({"column": c, "reason": f"目标列 {tc} 出现在特征列中"})

    hard = [v for v in violations if v.get("severity") != "warn"]
    ok = len(hard) == 0
    if not ok and raise_on_violation:
        raise LeakageError(f"任务 {task} 特征列违反泄漏防护策略: {hard}")
    return PolicyCheckResult(task=task, ok=ok, checked_columns=cols,
                             violations=violations, indirect_findings=[])


# ------------------------------------------------------------------ C 间接泄漏
# 参考字段分级：
#   * target  级（final_score / candidate_rank / candidate_rank_pct）——
#     它们直接决定 label_strength，特征若能近乎重建它们，判定为硬泄漏；
#   * component 级（semantic_score ... education_score / raw_score）——
#     它们是原评分公式的中间分量，特征与之一致只说明"复刻了原公式的一个分量"，
#     必须查明构造来源并记录，但不等同于目标泄漏（若构造确实只用原始字段）。
TARGET_LEVEL_REFERENCES = {"final_score", "candidate_rank", "candidate_rank_pct",
                           "label_strength", "label_ordinal"}
COMPONENT_LEVEL_REFERENCES = {"semantic_score", "skill_score", "position_score",
                              "category_score", "experience_score", "education_score",
                              "raw_score"}


def _finding_severity(ref_name: str) -> tuple[str, str]:
    if ref_name in TARGET_LEVEL_REFERENCES:
        return "hard", "target"
    if ref_name in COMPONENT_LEVEL_REFERENCES:
        return "warn", "component"
    return "warn", "other"


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def detect_indirect_leakage(feature_df: pd.DataFrame,
                            reference: dict[str, np.ndarray],
                            task: str,
                            spearman_threshold: float = 0.999,
                            r2_threshold: float = 0.999) -> list[dict]:
    """检测特征是否近乎确定地重建了禁止字段（间接泄漏）。

    reference: {禁止字段名: 该字段在同一批样本上的数值数组}

    严重度按参考字段分级：
      * final_score / candidate_rank / candidate_rank_pct 等 target 级字段被重建 -> hard；
      * semantic_score ... raw_score 等原公式中间分量被重建 -> warn（需查明构造来源，
        若特征确实只由原始字段独立构造，则属于"复刻原公式分量"而非目标泄漏，必须记录）。
    """
    findings: list[dict] = []
    num = feature_df.select_dtypes(include=[np.number])
    if num.shape[1] == 0 or not reference:
        return findings

    X = num.to_numpy(dtype=np.float64)
    names = list(num.columns)
    finite = np.isfinite(X)
    if not finite.all():
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    for ref_name, ref_arr in reference.items():
        sev, level = _finding_severity(ref_name)
        y = np.asarray(ref_arr, dtype=np.float64).ravel()
        if y.size != X.shape[0]:
            findings.append({"reference": ref_name, "code": "LENGTH_MISMATCH",
                             "severity": sev, "reference_level": level})
            continue
        # 1) 单列近乎完全单调相关
        for j, name in enumerate(names):
            rho = abs(_spearman(X[:, j], y))
            if rho >= spearman_threshold:
                findings.append({"reference": ref_name, "column": name,
                                 "code": "NEAR_DETERMINISTIC_MONOTONIC",
                                 "abs_spearman": round(rho, 6),
                                 "severity": sev, "reference_level": level})
        # 2) 线性重建 R^2
        try:
            A = np.hstack([X, np.ones((X.shape[0], 1))])
            coef, *_ = np.linalg.lstsq(A, y, rcond=None)
            pred = A @ coef
            ss_res = float(np.sum((y - pred) ** 2))
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
            if r2 >= r2_threshold:
                findings.append({"reference": ref_name, "code": "LINEAR_RECONSTRUCTION",
                                 "r2": round(r2, 6),
                                 "severity": sev, "reference_level": level})
        except np.linalg.LinAlgError:
            findings.append({"reference": ref_name, "code": "LSTSQ_FAILED",
                             "severity": "warn", "reference_level": level})
    return findings


# ------------------------------------------------------------------ 统一入口
def audit_feature_set(task: str, feature_df: pd.DataFrame,
                      reference: dict[str, np.ndarray] | None = None,
                      raise_on_violation: bool = True,
                      allow_uncertain: bool = False) -> PolicyCheckResult:
    """对一个实际构建出来的特征 DataFrame 做完整泄漏审计。"""
    res = check_feature_columns(task, list(feature_df.columns),
                                raise_on_violation=raise_on_violation,
                                allow_uncertain=allow_uncertain)
    if reference:
        res.indirect_findings = detect_indirect_leakage(feature_df, reference, task)
        hard = [f for f in res.indirect_findings if f.get("severity") != "warn"]
        if hard:
            res.ok = False
            if raise_on_violation:
                raise LeakageError(f"任务 {task} 检出间接泄漏: {hard}")
    return res


def assert_tensor_features(task: str, feature_names: list[str],
                           tensor_shape: tuple[int, ...]) -> None:
    """对 Tensor 特征矩阵做列名与维度一致性核验（G3 的 Tensor 侧检查）。"""
    if len(feature_names) != tensor_shape[-1]:
        raise LeakageError(
            f"特征名数量 {len(feature_names)} 与 Tensor 最后一维 {tensor_shape[-1]} 不一致")
    check_feature_columns(task, feature_names, raise_on_violation=True)
