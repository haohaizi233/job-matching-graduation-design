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
# 冻结前置 / 冻结后置两阶段门禁（Phase5-1R F-001）。
#
# 历史缺陷：facts 初始化 split_isolation_ok=False / freeze_verified=False，
# 而切分与冻结恰好发生在 G2 检查之后，导致「未冻结 -> 不过门禁 -> 不能冻结」的
# 循环依赖，真实数据到位后正常入口仍无法进入成功路径。
#
# 修复口径（一套规则、两阶段调用，禁止同一规则实现两份）：
#   * evaluate_precheck  —— 冻结前置检查：授权、规模、双人标注、标注独立性、
#                           分歧仲裁、unjudgeable 保护、阻断性泄漏、合成混入、
#                           来源与许可。此阶段**不得**要求已有冻结哈希；
#   * evaluate_postcheck —— 冻结后验证：切分隔离、pair 唯一、最终标签一一对应、
#                           文件完整、SHA-256 复验、数据集版本、来源记录；
#   * evaluate_g2_status —— H2 汇总判定 = 前置 + 后置 + 真实规模门槛。
#
# strict 语义（只控制「事实缺失」的处理，不改变任何规则）：
#   * strict=True  （冻结流程调用）：缺少事实一律按不满足处理并登记 missing_fact；
#   * strict=False （历史 facts 契约）：缺失事实按**文档化不变量**推导，
#     推导关系写入 checks[*].derived_from，供审计核对，不做静默放行。

ARBITRATION_STATUSES = ("not_required", "pending", "completed", "invalid")

_PRECHECK_RULES = (
    "consent_complete", "source_license_ok", "real_resumes", "real_pairs",
    "dual_annotation_complete", "annotator_independence_ok", "open_disagreements",
    "arbitration_status", "unjudgeable_forced", "blocking_findings",
    "synthetic_pairs_included",
)

_POSTCHECK_RULES = (
    "split_isolation_ok", "pair_id_unique", "resume_job_unique",
    "final_labels_complete", "final_labels_unique", "final_label_pairs_known",
    "files_complete", "sha256_ok", "dataset_version_ok", "provenance_complete",
)


def _fact(facts: dict, key: str, default, *, strict: bool,
          derived_from: str = "") -> tuple[object, dict]:
    """取事实值：strict 下缺失即视为不满足；非 strict 下用文档化不变量推导。

    返回 (值, meta)；meta.missing=True 表示该事实在输入中缺失，
    meta.derived_from 记录推导依据或 missing_fact:<key>，供审计核对。
    """
    if key in facts:
        return facts[key], {"missing": False, "derived_from": ""}
    if strict:
        return default, {"missing": True, "derived_from": f"missing_fact:{key}"}
    return default, {"missing": True,
                     "derived_from": derived_from or f"legacy_default:{key}"}


def evaluate_precheck(facts: dict, *, min_real_pairs: int = H2_MIN_REAL_PAIRS,
                      strict: bool = True) -> dict:
    """Pre-freeze Gate：冻结前置检查（不要求任何冻结哈希/切分结果）。

    facts 键（strict=True 时全部必须显式提供）：
      consent_complete, source_license_ok, real_resumes, real_pairs,
      dual_annotation_complete, annotator_independence_ok, open_disagreements,
      arbitration_status, unjudgeable_forced, blocking_findings,
      synthetic_pairs_included
    """
    checks: dict[str, dict] = {}
    reasons: list[str] = []

    def _bool_rule(key: str, ok_when: bool, reason: str, derived_from: str = "") -> None:
        raw, meta = _fact(facts, key, not ok_when if strict else ok_when, strict=strict,
                          derived_from=derived_from)
        ok = bool(raw) is ok_when
        checks[key] = {"ok": ok, "value": raw, **meta}
        if not ok:
            reasons.append(reason)

    _bool_rule("consent_complete", True,
               "真实数据授权记录不完整（consent 未全部 granted/licensed）")
    _bool_rule("source_license_ok", True,
               "数据来源与使用许可不满足准入（source/license 缺失或失效）")

    real_resumes, meta = _fact(facts, "real_resumes", 0, strict=strict)
    real_resumes = int(real_resumes or 0)
    checks["real_resumes"] = {"ok": real_resumes > 0, "value": real_resumes, **meta}
    if real_resumes <= 0:
        reasons.append("真实中文简历 0 份：无法建立真实人岗配对与人工 Gold")

    real_pairs, meta = _fact(facts, "real_pairs", 0, strict=strict)
    real_pairs = int(real_pairs or 0)
    pairs_ok = real_pairs > 0 and real_pairs >= int(min_real_pairs)
    checks["real_pairs"] = {"ok": pairs_ok, "value": real_pairs, **meta}
    if real_pairs <= 0:
        reasons.append("真实有效配对 0 组：双盲标注与 Gold 冻结无对象")
    elif real_pairs < int(min_real_pairs):
        reasons.append(f"真实有效配对 {real_pairs} 组 < {min_real_pairs}（{H2_TARGET_NOTE}）")

    _bool_rule("dual_annotation_complete", True,
               "双人独立标注未完成（annotation_status != complete）")
    _bool_rule("annotator_independence_ok", True,
               "标注员独立性检查未通过（同一人冒充两名标注员或整表镜像）",
               derived_from="dual_annotation_complete(标注完成状态已包含独立性通过)")

    open_dis, meta = _fact(facts, "open_disagreements", 0, strict=strict)
    open_dis = int(open_dis or 0)
    checks["open_disagreements"] = {"ok": open_dis == 0, "value": open_dis, **meta}
    if open_dis > 0:
        reasons.append(f"仍有 {open_dis} 组分歧未仲裁")

    arb, meta = _fact(facts, "arbitration_status",
                      "completed" if open_dis == 0 else "pending", strict=strict,
                      derived_from="open_disagreements(无分歧 => not_required/completed)")
    arb = str(arb or "")
    arb_ok = arb in ("not_required", "completed")
    checks["arbitration_status"] = {"ok": arb_ok, "value": arb, **meta}
    if arb == "pending":
        reasons.append("存在未完成仲裁的分歧样本")
    elif arb == "invalid":
        reasons.append("仲裁记录非法（协议不符/重复/来源不明），不得据此宣布完成")
    elif arb not in ARBITRATION_STATUSES:
        reasons.append(f"仲裁状态非法: {arb!r}，合法值 {ARBITRATION_STATUSES}")

    unj, meta = _fact(facts, "unjudgeable_forced", 0, strict=strict)
    unj = int(unj or 0)
    checks["unjudgeable_forced"] = {"ok": unj == 0, "value": unj, **meta}
    if unj > 0:
        reasons.append("存在 unjudgeable 被强行归类的记录")

    block, meta = _fact(facts, "blocking_findings",
                        facts.get("leakage_blocking_findings"), strict=strict,
                        derived_from="leakage_blocking_findings(历史事实名)")
    block = list(block or [])
    checks["blocking_findings"] = {"ok": not block, "value": len(block), **meta}
    if block:
        reasons.append("存在阻断性泄漏/重复风险未处理: " + "; ".join(map(str, block)))

    syn, meta = _fact(facts, "synthetic_pairs_included", 0, strict=strict,
                      derived_from="legacy 合成样本只登记为 excluded，默认未混入")
    syn = int(syn or 0)
    checks["synthetic_pairs_included"] = {"ok": syn == 0, "value": syn, **meta}
    if syn > 0:
        reasons.append(f"存在 {syn} 组合成配对混入人工 Gold（合成数据不得进入真值集）")

    return {
        "stage": "pre_freeze",
        "status": "blocked" if reasons else "ready",
        "precheck_passed": not reasons,
        "reasons": reasons,
        "checks": checks,
        "facts": {"real_resumes": real_resumes, "real_pairs": real_pairs,
                  "min_real_pairs": int(min_real_pairs),
                  "synthetic_pairs": int(facts.get("synthetic_pairs", 0) or 0)},
    }


def evaluate_postcheck(facts: dict, *, strict: bool = True) -> dict:
    """Post-freeze Gate：冻结后验证（切分、唯一性、标签、文件、哈希、版本、来源）。"""
    checks: dict[str, dict] = {}
    reasons: list[str] = []
    freeze_verified = bool(facts.get("freeze_verified", False))

    def _bool_rule(key: str, reason: str, derived_from: str = "") -> None:
        raw, meta = _fact(facts, key, freeze_verified if not strict else False,
                          strict=strict, derived_from=derived_from)
        ok = bool(raw)
        checks[key] = {"ok": ok, "value": raw, **meta}
        if not ok:
            reasons.append(reason)

    _bool_rule("split_isolation_ok", "dev_validation / blind_test 分组隔离检查未通过")
    _bool_rule("pair_id_unique", "存在重复 pair_id，冻结拒绝",
               derived_from="freeze_verified(冻结互斥检查为硬性条件)")
    _bool_rule("resume_job_unique", "存在重复 (resume_id, job_id) 配对，冻结拒绝",
               derived_from="freeze_verified(冻结互斥检查为硬性条件)")
    _bool_rule("final_labels_complete", "存在缺少最终标签的配对，冻结拒绝",
               derived_from="freeze_verified(冻结互斥检查为硬性条件)")
    _bool_rule("final_labels_unique", "同一 pair 存在多个最终标签，冻结拒绝",
               derived_from="freeze_verified(冻结互斥检查为硬性条件)")
    _bool_rule("final_label_pairs_known", "最终标签引用未知 pair，冻结拒绝",
               derived_from="freeze_verified(冻结互斥检查为硬性条件)")
    _bool_rule("files_complete", "冻结所需文件缺失，冻结拒绝",
               derived_from="freeze_verified(缺失文件无法通过 SHA-256 复验)")
    _bool_rule("sha256_ok", "评估集未冻结或哈希复验未通过")
    _bool_rule("dataset_version_ok", "数据集版本冲突或版本记录缺失",
               derived_from="freeze_verified(冻结 manifest 必带 dataset_version)")
    _bool_rule("provenance_complete", "冻结清单缺少完整的来源记录",
               derived_from="freeze_verified(responsibility 为冻结硬性条件)")

    return {
        "stage": "post_freeze",
        "status": "failed" if reasons else "passed",
        "postcheck_passed": not reasons,
        "split_validated": bool(checks["split_isolation_ok"]["ok"]),
        "freeze_written": bool(facts.get("freeze_written", freeze_verified)),
        "freeze_verified": freeze_verified,
        "reasons": reasons,
        "checks": checks,
    }


def evaluate_g2_status(facts: dict, *, min_real_pairs: int = H2_MIN_REAL_PAIRS,
                       strict: bool = False) -> dict:
    """G2（真实 Gold 评估集正式冻结）状态判定（测试场景 16 / Phase5-1R F-001）。

    = evaluate_precheck + evaluate_postcheck + 真实规模门槛，输出保持历史契约：
    {"status": "ready"|"blocked", "reasons": [...], "facts": {...}}。

    facts 键（历史契约，全部保留原语义）：
      real_resumes, real_pairs, synthetic_pairs, dual_annotation_complete,
      open_disagreements, unjudgeable_forced, consent_complete,
      leakage_blocking_findings, split_isolation_ok, freeze_verified
    扩展键（冻结流程显式传入，strict=True 时必须齐全）：
      source_license_ok, annotator_independence_ok, arbitration_status,
      synthetic_pairs_included, pair_id_unique, resume_job_unique,
      final_labels_complete, final_labels_unique, final_label_pairs_known,
      files_complete, sha256_ok, dataset_version_ok, provenance_complete
    任何不满足项都进入 reasons；无真实数据时必须 BLOCKED。
    """
    pre = evaluate_precheck(facts, min_real_pairs=min_real_pairs, strict=strict)
    post = evaluate_postcheck(facts, strict=strict)
    reasons = list(pre["reasons"]) + [r for r in post["reasons"]
                                      if r not in pre["reasons"]]
    return {
        "status": "blocked" if reasons else "ready",
        "reasons": reasons,
        "precheck": pre,
        "postcheck": post,
        "facts": {
            "real_resumes": int(facts.get("real_resumes", 0) or 0),
            "real_pairs": int(facts.get("real_pairs", 0) or 0),
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
