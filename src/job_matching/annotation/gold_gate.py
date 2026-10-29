# -*- coding: utf-8 -*-
"""Gold 评估集门禁：配对完整性、切分隔离、真实 Gold 计数、G2 状态、盲测保护
（Phase4-3A-2 模块 C/E / 测试场景 4、5、6、7、14、16、17）。

硬性规则：
  * pair_id 唯一、(resume_id, job_id) 唯一，重复直接拒绝；
  * 同一 resume_id 不得跨 dev_validation / blind_test（组级切分）；
  * 与训练语料交叉的岗位必须显式标记，不得混入要求「模型未见过岗位文本」的盲测集；
  * 真实 Gold 计数**只**统计真实、授权、中文记录，合成数据永不计入；
  * 无真实简历/真实标注时 G2 必须 BLOCKED；
  * 冻结完成前 blind_test 不得被标记为正式通过。
"""
from __future__ import annotations

from . import dedup as dedup_mod

SPLIT_DEV = "dev_validation"
SPLIT_BLIND = "blind_test"
SPLITS = (SPLIT_DEV, SPLIT_BLIND)

H2_MIN_REAL_PAIRS = 300
H2_TARGET_NOTE = "真实配对目标 300–600 组（任务书模块 C）"


class GateError(ValueError):
    """Gold 门禁违规。code 用于测试与报告分类。"""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


# ------------------------------------------------------------------ 配对完整性
def ensure_unique_pair_ids(pairs: list[dict]) -> None:
    """重复 pair_id / 重复 (resume_id, job_id) 直接拒绝（测试场景 4）。"""
    seen_ids: dict[str, str] = {}
    seen_rj: dict[tuple[str, str], str] = {}
    for p in pairs:
        pid = str(p.get("pair_id", ""))
        key = (str(p.get("resume_id", "")), str(p.get("job_id", "")))
        if not pid:
            raise GateError("missing_pair_id", "存在空 pair_id")
        if pid in seen_ids:
            raise GateError("duplicate_pair_id", f"重复 pair_id: {pid}")
        if key in seen_rj:
            raise GateError("duplicate_resume_job_pair",
                            f"重复 (resume_id, job_id) 配对: {key}（pair_id {pid} 与 {seen_rj[key]}）")
        seen_ids[pid] = pid
        seen_rj[key] = pid


def quarantine_near_duplicates(pairs: list[dict], threshold: float = 0.90
                               ) -> tuple[list[dict], list[dict]]:
    """配对级近似重复隔离（测试场景 7）：保留首条（按 pair_id 排序），其余隔离并带原因。

    返回 (kept, quarantined)；quarantined 元素含 quarantine_reason=near_duplicate_pair
    与 dup_of。近似重复判定口径见 dedup.near_duplicate_pairs（shingle Jaccard >= threshold）。
    """
    ordered = sorted(pairs, key=lambda p: str(p.get("pair_id", "")))
    index = dedup_mod.DuplicateIndex(threshold=float(threshold))
    kept: list[dict] = []
    quarantined: list[dict] = []
    for p in ordered:
        text = f"{p.get('resume_text', '')}\x1f{p.get('job_text', '')}"
        res = index.check(str(p.get("pair_id", "")), text)
        if res["status"] == "unique":
            kept.append(dict(p))
        else:
            q = dict(p)
            q["quarantine_reason"] = ("duplicate_pair_text" if res["status"] in
                                      ("exact_dup", "norm_dup") else "near_duplicate_pair")
            q["dup_of"] = res["dup_of"]
            q["dup_similarity"] = res["similarity"]
            quarantined.append(q)
    return kept, quarantined


def flag_training_overlap(pairs: list[dict], overlap_job_ids: set[str] | list[str],
                          *, reason: str = "training_corpus_overlap") -> list[dict]:
    """训练数据交叉检查（测试场景 6）：命中训练语料重合的岗位 → 标记并禁入盲测集。

    返回新列表（不修改输入）；命中记录带 training_overlap=true、blind_eligible=false、
    training_overlap_reason。不把「不同训练任务的语料重合」一概当泄漏，由调用方
    按任务传入 overlap_job_ids 并在报告中分别说明影响面。
    """
    hit = {str(j) for j in overlap_job_ids}
    out = []
    for p in pairs:
        q = dict(p)
        if str(q.get("job_id", "")) in hit:
            q["training_overlap"] = True
            q["blind_eligible"] = False
            q["training_overlap_reason"] = reason
        else:
            q.setdefault("training_overlap", False)
            q.setdefault("blind_eligible", True)
        out.append(q)
    return out


# ------------------------------------------------------------------ 切分隔离
def check_split_isolation(pairs: list[dict], *, job_isolated: bool = False) -> dict:
    """组级切分隔离检查（测试场景 5）：同一 resume_id 不得跨 dev/blind。

    job_isolated=True 时额外检查岗位级隔离（岗位冷启动/双冷启动协议用）。
    """
    by_resume: dict[str, set[str]] = {}
    by_job: dict[str, set[str]] = {}
    for p in pairs:
        sp = str(p.get("split", ""))
        if sp not in SPLITS:
            continue
        by_resume.setdefault(str(p.get("resume_id", "")), set()).add(sp)
        by_job.setdefault(str(p.get("job_id", "")), set()).add(sp)
    resume_overlap = sorted(rid for rid, sps in by_resume.items() if len(sps) > 1)
    job_overlap = sorted(jid for jid, sps in by_job.items() if len(sps) > 1)
    split_sizes = {}
    for p in pairs:
        sp = str(p.get("split", ""))
        split_sizes[sp] = split_sizes.get(sp, 0) + 1
    ok = not resume_overlap and (not job_isolated or not job_overlap)
    return {
        "ok": bool(ok),
        "isolation": "job_and_resume" if job_isolated else "resume_group_only",
        "resume_overlap": resume_overlap[:100],
        "resume_overlap_count": len(resume_overlap),
        "job_overlap": job_overlap[:100],
        "job_overlap_count": len(job_overlap),
        "split_sizes": dict(sorted(split_sizes.items())),
        "resumes": len(by_resume),
        "jobs": len(by_job),
        "note": ("仅按简历 ID 组级隔离；不得称为岗位冷启动或双冷启动。"
                 "如需岗位冷启动，必须按 job_id 严格隔离另行建协议"
                 if not job_isolated else "岗位级隔离协议"),
    }


# ------------------------------------------------------------------ 真实 Gold 计数
def is_real_gold_record(rec: dict) -> bool:
    """真实 Gold 记录判定：非合成 + 授权 granted/licensed + 中文 + 非隔离。"""
    if bool(rec.get("is_synthetic")):
        return False
    if str(rec.get("consent_status", "")).strip().lower() not in ("granted", "licensed"):
        return False
    if rec.get("eligible_for_gold") is False:
        return False
    if str(rec.get("quarantine_reason", "")).strip():
        return False
    if rec.get("language") not in ("zh", "mixed", None, ""):
        return False
    return True


def count_real_gold(records: list[dict]) -> dict:
    """真实 Gold 计数（测试场景 17）：合成数据永不计入真实数量。"""
    real = [r for r in records if is_real_gold_record(r)]
    synthetic = [r for r in records if bool(r.get("is_synthetic"))]
    other = [r for r in records if not is_real_gold_record(r) and not bool(r.get("is_synthetic"))]
    return {
        "real_gold": len(real),
        "synthetic_excluded": len(synthetic),
        "non_gold_excluded": len(other),
        "total_records": len(records),
        "note": "合成样本、未授权、非中文、被隔离记录一律不计入真实 Gold 数量",
    }


# ------------------------------------------------------------------ G2 门禁
def evaluate_g2_status(facts: dict, *, min_real_pairs: int = H2_MIN_REAL_PAIRS) -> dict:
    """G2（真实 Gold 评估集正式冻结）状态判定（测试场景 16）。

    facts 键：
      real_resumes, real_pairs, synthetic_pairs, dual_annotation_complete,
      open_disagreements, unjudgeable_forced, consent_complete,
      leakage_blocking_findings, split_isolation_ok, freeze_verified
    任何不满足项都进入 reasons；无真实数据时必须 BLOCKED。
    """
    reasons: list[str] = []
    real_resumes = int(facts.get("real_resumes", 0) or 0)
    real_pairs = int(facts.get("real_pairs", 0) or 0)
    if real_resumes <= 0:
        reasons.append("真实中文简历 0 份：无法建立真实人岗配对与人工 Gold")
    if real_pairs <= 0:
        reasons.append("真实有效配对 0 组：双盲标注与 Gold 冻结无对象")
    elif real_pairs < int(min_real_pairs):
        reasons.append(f"真实有效配对 {real_pairs} 组 < {min_real_pairs}（{H2_TARGET_NOTE}）")
    if not bool(facts.get("dual_annotation_complete", False)):
        reasons.append("双人独立标注未完成（annotation_status != complete）")
    if int(facts.get("open_disagreements", 0) or 0) > 0:
        reasons.append(f"仍有 {facts.get('open_disagreements')} 组分歧未仲裁")
    if int(facts.get("unjudgeable_forced", 0) or 0) > 0:
        reasons.append("存在 unjudgeable 被强行归类的记录")
    if not bool(facts.get("consent_complete", False)):
        reasons.append("真实数据授权记录不完整（consent 未全部 granted/licensed）")
    if facts.get("leakage_blocking_findings"):
        reasons.append("存在阻断性泄漏/重复风险未处理: "
                       + "; ".join(map(str, facts.get("leakage_blocking_findings"))))
    if not bool(facts.get("split_isolation_ok", False)):
        reasons.append("dev_validation / blind_test 分组隔离检查未通过")
    if not bool(facts.get("freeze_verified", False)):
        reasons.append("评估集未冻结或哈希复验未通过")
    return {
        "status": "blocked" if reasons else "ready",
        "reasons": reasons,
        "facts": {
            "real_resumes": real_resumes,
            "real_pairs": real_pairs,
            "synthetic_pairs": int(facts.get("synthetic_pairs", 0) or 0),
            "min_real_pairs": int(min_real_pairs),
        },
    }


# ------------------------------------------------------------------ 盲测保护
def check_blind_status(*, freeze_verified: bool, blind_claimed_pass: bool) -> dict:
    """盲测保护（测试场景 14）：冻结完成前 blind_test 不得被标记正式通过。"""
    violations = []
    if bool(blind_claimed_pass) and not bool(freeze_verified):
        violations.append({
            "code": "blind_pass_before_freeze",
            "message": "评估集冻结/哈希复验未完成，blind_test 不得被标记为正式通过",
        })
    return {"ok": not violations, "violations": violations,
            "freeze_verified": bool(freeze_verified),
            "blind_claimed_pass": bool(blind_claimed_pass)}
