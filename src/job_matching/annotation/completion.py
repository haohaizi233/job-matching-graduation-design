# -*- coding: utf-8 -*-
"""标注完成状态与仲裁状态判定（Phase5-1R F-002 / F-003）。

历史缺陷：`annotation_qa` 只把「缺失标注 = 0 + 无未决分歧 + 无 unjudgeable 违规」
累成布尔表达式就宣布 `complete`，标注员独立性、导入错误、仲裁协议、最终标签
一一对应等检查**只写报告不阻断**，出现「系统记录了风险，但没有阻止风险」。

本模块把「标注完成」定义为 10 项硬性条件同时成立（缺一不可）：

  1. 所有待评估配对均具备符合协议的双人标注；
  2. 两个标注员身份不同；
  3. 标注协议版本一致；
  4. 标注文件不存在阻断性导入错误；
  5. 标注独立性检查通过（共享 ID / 整表镜像直接阻断）；
  6. 所有需要仲裁的样本均已完成仲裁；
  7. 仲裁记录符合协议（不合规即 invalid）；
  8. 未发生 unjudgeable 违规转换；
  9. 最终标签与 pair_id 一对一关联；
  10. 不存在非法、重复或来源不明的标签。

状态取值（唯一口径）：
  pending / in_progress / needs_review / blocked / complete

注意：两名标注员给出**相同标签**本身不构成违规（可能确有共识）；
只有整份标注记录逐字镜像（标签/置信度/理由/证据/时间戳全同）才触发独立性阻断，
部分镜像触发人工审查（needs_review）。禁止用「标签相同」当抄袭证据。
"""
from __future__ import annotations

from .schema import PROTOCOL_VERSION

ANNOTATION_STATUSES = ("pending", "in_progress", "needs_review", "blocked", "complete")
ARBITRATION_STATUSES = ("not_required", "pending", "completed", "invalid")

# 独立性违规中直接阻断的码（其余进入人工审查）
_BLOCKING_INDEPENDENCE_CODES = ("shared_annotator_id", "mirrored_annotations")
_REVIEW_INDEPENDENCE_CODES = ("partially_mirrored_annotations",)


def assess_arbitration_status(*, disagreements: list[dict],
                              arbitration_rows: list[dict] | None = None,
                              arbitration_report: dict | None = None) -> dict:
    """仲裁状态判定：not_required / pending / completed / invalid。

    规则（F-003）：
      * 分歧数 = 0 -> not_required：不得强制要求人工仲裁文件；
        此时若出现仲裁记录，必须说明原因并阻止其改写已一致的标签；
      * 分歧数 > 0 -> 必须有合法仲裁记录，且 pair_id 集合与分歧集合一一对应：
        漏掉任一未决分歧 -> pending；记录非法/重复/越权 -> invalid；
      * 禁止用虚假的「已人工仲裁」记录绕过门禁（越权改写一致结论 -> invalid）。
    """
    rows = list(arbitration_rows or [])
    rep = dict(arbitration_report or {})
    errors = list(rep.get("errors") or [])
    warnings = list(rep.get("warnings") or [])
    disputed = {str(d.get("pair_id", "")) for d in (disagreements or [])}
    arbitrated = [str(r.get("pair_id", "")) for r in rows]
    reasons: list[str] = []

    override_attempts = [str(r.get("pair_id", "")) for r in rows
                         if str(r.get("_override_attempt", ""))]
    # 越权仲裁：仲裁记录覆盖「两人已一致」的结论（由调用方在 _override_attempt 标注）
    if override_attempts:
        reasons.append("存在越权仲裁记录（试图改写双方已一致的结论）: "
                       + ", ".join(override_attempts[:20]))

    if override_attempts:
        # 越权仲裁一律 invalid：无论是否存在分歧，仲裁记录都不得改写双方一致的结论
        status = "invalid"
    elif not disputed:
        status = "not_required"
        if rows:
            reasons.append(
                f"无分歧样本却存在 {len(rows)} 条仲裁记录；"
                f"仲裁记录不得改写双方一致的结论（保留记录并人工复核）")
        if errors:
            status = "invalid"
            reasons.append(f"仲裁文件存在 {len(errors)} 条非法记录: "
                           + "; ".join(str(e.get("message", e)) for e in errors[:10]))
    else:
        if errors:
            status = "invalid"
            reasons.append(f"仲裁文件存在 {len(errors)} 条非法记录: "
                           + "; ".join(str(e.get("message", e)) for e in errors[:10]))
        elif set(arbitrated) >= disputed:
            status = "completed"
            extra = sorted(set(arbitrated) - disputed)
            if extra:
                reasons.append(f"仲裁记录包含无分歧样本 {extra[:20]}（保留但标记复核）")
        else:
            status = "pending"
            missing = sorted(disputed - set(arbitrated))
            reasons.append(f"{len(missing)} 组分歧尚未仲裁: {missing[:20]}")

    return {
        "status": status,
        "reasons": reasons,
        "disagreements_total": len(disputed),
        "arbitration_rows": len(rows),
        "arbitrated_pairs": sorted(set(arbitrated)),
        "unresolved_pairs": sorted(disputed - set(arbitrated)) if disputed else [],
        "import_errors": len(errors),
        "import_warnings": len(warnings),
        "note": ("分歧为 0 时不强制要求人工仲裁文件；分歧 > 0 时仲裁记录必须"
                 "与分歧集合一一对应，禁止虚假仲裁记录绕过门禁"),
    }


def check_final_label_integrity(pairs: list[dict], final_rows: list[dict]) -> dict:
    """最终标签与 pair_id 一对一关联检查（条件 9/10）。"""
    pair_ids = [str(p.get("pair_id", "")) for p in pairs]
    label_ids = [str(r.get("pair_id", "")) for r in final_rows]
    seen: set[str] = set()
    duplicates: list[str] = []
    for pid in label_ids:
        if pid in seen:
            duplicates.append(pid)
        seen.add(pid)
    unknown = sorted(seen - set(pair_ids))
    missing = sorted(set(pair_ids) - seen)
    unfinalized = sorted(str(r.get("pair_id", "")) for r in final_rows
                         if str(r.get("final_relevance", "") or "").strip() == "")
    invalid_labels = sorted(
        str(r.get("pair_id", "")) for r in final_rows
        if str(r.get("final_relevance", "") or "").strip() not in ("", "0", "1", "2", "unjudgeable"))
    problems: list[str] = []
    if duplicates:
        problems.append(f"最终标签重复 pair_id: {sorted(set(duplicates))[:20]}")
    if unknown:
        problems.append(f"最终标签引用未知 pair: {unknown[:20]}")
    if missing:
        problems.append(f"{len(missing)} 个配对缺少最终标签: {missing[:20]}")
    if invalid_labels:
        problems.append(f"最终标签取值非法: {invalid_labels[:20]}")
    return {
        "ok": not problems,
        "pairs_total": len(pair_ids),
        "labels_total": len(label_ids),
        "duplicate_pair_ids": sorted(set(duplicates)),
        "unknown_pair_ids": unknown,
        "missing_pair_ids": missing,
        "unfinalized_pair_ids": unfinalized,
        "invalid_label_pair_ids": invalid_labels,
        "problems": problems,
    }


def assess_annotation_completion(*, pairs: list[dict],
                                 rows_by_annotator: dict[str, list[dict]],
                                 import_reports: dict[str, dict] | None = None,
                                 independence: dict | None = None,
                                 final_rows: list[dict] | None = None,
                                 arbitration_status: str = "not_required",
                                 unjudgeable_forced: list[dict] | None = None,
                                 disagreements: list[dict] | None = None,
                                 protocol_version: str = PROTOCOL_VERSION) -> dict:
    """标注完成状态判定（唯一实现，脚本不得再堆积布尔表达式）。"""
    rows_by_annotator = dict(rows_by_annotator or {})
    import_reports = dict(import_reports or {})
    independence = dict(independence or {})
    final_rows = list(final_rows or [])
    unjudgeable_forced = list(unjudgeable_forced or [])
    disagreements = list(disagreements or [])

    blocking: list[str] = []
    review: list[str] = []
    checks: dict[str, dict] = {}

    all_rows = [r for rows in rows_by_annotator.values() for r in rows]
    annotators = sorted(rows_by_annotator)
    checks["annotators_registered"] = {"ok": len(annotators) >= 2, "value": annotators}
    if len(annotators) < 2:
        blocking.append(f"独立标注员不足 2 人（当前 {annotators or '无'}）")

    # 条件 2/5：标注员身份不同 + 独立性
    indep_violations = list(independence.get("violations") or [])
    indep_codes = {str(v.get("code", "")) for v in indep_violations}
    blocking_codes = sorted(indep_codes & set(_BLOCKING_INDEPENDENCE_CODES))
    review_codes = sorted(indep_codes & set(_REVIEW_INDEPENDENCE_CODES))
    checks["annotator_independence"] = {
        "ok": not indep_violations,
        "status": independence.get("status"),
        "violations": [v.get("code") for v in indep_violations],
    }
    for v in indep_violations:
        if str(v.get("code", "")) in _BLOCKING_INDEPENDENCE_CODES:
            blocking.append(f"标注独立性阻断[{v.get('code')}]: {v.get('message')}")
        else:
            review.append(f"标注独立性待复核[{v.get('code')}]: {v.get('message')}")
    checks["annotator_independence"]["blocking_codes"] = blocking_codes
    checks["annotator_independence"]["review_codes"] = review_codes

    # 条件 4：导入错误阻断（不得忽略错误行后宣布完成）
    import_error_total = 0
    import_warning_total = 0
    per_file: dict[str, dict] = {}
    for name, rep in import_reports.items():
        errs = list(rep.get("errors") or [])
        warns = list(rep.get("warnings") or [])
        import_error_total += len(errs)
        import_warning_total += len(warns)
        per_file[name] = {"errors": len(errs), "warnings": len(warns),
                          "status": rep.get("status", "")}
        if errs:
            blocking.append(f"标注导入存在 {len(errs)} 条非法记录（{name}）: "
                            + "; ".join(str(e.get("message", e)) for e in errs[:5]))
        if warns:
            review.append(f"标注导入存在 {len(warns)} 条需复核记录（{name}）: "
                          + "; ".join(str(w.get("message", w)) for w in warns[:5]))
    checks["import_reports"] = {"ok": import_error_total == 0,
                                "errors": import_error_total,
                                "warnings": import_warning_total,
                                "files": per_file}

    # 条件 1/3：双人标注齐全 + 协议版本一致
    by_pair: dict[str, set[str]] = {}
    for r in all_rows:
        by_pair.setdefault(str(r.get("pair_id", "")), set()).add(str(r.get("annotator_id", "")))
    missing_pairs = [str(p.get("pair_id", "")) for p in pairs
                     if len(by_pair.get(str(p.get("pair_id", "")), set())) < 2]
    extra_pairs = sorted(set(by_pair) - {str(p.get("pair_id", "")) for p in pairs})
    checks["dual_annotation"] = {
        "ok": not missing_pairs and not extra_pairs,
        "pairs_total": len(pairs),
        "pairs_missing": len(missing_pairs),
        "missing_pair_ids": missing_pairs[:20],
        "unknown_pair_ids": extra_pairs[:20],
    }
    # 缺失标注 = 未完成（不填补默认标签、不阻断保存，但绝不允许宣布 complete）
    incomplete: list[str] = []
    if missing_pairs:
        incomplete.append(f"{len(missing_pairs)} 个配对缺少双人标注（只登记不填补）")
    if extra_pairs:
        blocking.append(f"标注记录引用未知 pair: {extra_pairs[:20]}")

    protocol_versions = sorted({str(r.get("protocol_version", "")) for r in all_rows
                                if str(r.get("protocol_version", ""))})
    pv_ok = (not protocol_versions) or protocol_versions == [protocol_version]
    checks["protocol_version"] = {"ok": pv_ok, "value": protocol_versions}
    if not pv_ok:
        blocking.append(f"标注协议版本不一致: {protocol_versions}（期望 {protocol_version}）")

    # 条件 6/7：仲裁
    arb_ok = arbitration_status in ("not_required", "completed")
    checks["arbitration_status"] = {"ok": arb_ok, "value": arbitration_status}
    if arbitration_status == "pending":
        incomplete.append("存在未完成仲裁的分歧样本（保持未完成，不得宣布标注完成）")
    elif arbitration_status == "invalid":
        blocking.append("仲裁记录非法（协议不符/重复/越权改写一致结论），标注状态阻断")
    elif arbitration_status not in ARBITRATION_STATUSES:
        blocking.append(f"仲裁状态非法: {arbitration_status!r}，合法值 {ARBITRATION_STATUSES}")

    # 条件 8：unjudgeable 保护
    checks["unjudgeable_forced"] = {"ok": not unjudgeable_forced,
                                    "value": len(unjudgeable_forced)}
    for p in unjudgeable_forced:
        blocking.append(f"unjudgeable 违规转换: {p.get('pair_id')} {p.get('message', '')}")

    # 条件 9/10：最终标签一对一
    integrity = check_final_label_integrity(pairs, final_rows) if pairs else {
        "ok": True, "problems": [], "unfinalized_pair_ids": []}
    checks["final_label_integrity"] = integrity
    if not integrity.get("ok", True):
        blocking.extend(integrity.get("problems") or [])
    unfinalized = [pid for pid in integrity.get("unfinalized_pair_ids", [])]
    if unfinalized:
        incomplete.append(f"{len(unfinalized)} 个配对最终标签为空（未完成仲裁）")

    # ---- 状态汇总
    counts = {
        "pairs_total": len(pairs),
        "annotation_rows": len(all_rows),
        "disagreements": len(disagreements),
        "blocking_findings": len(blocking),
        "review_findings": len(review),
        "incomplete_findings": len(incomplete),
    }
    if not pairs:
        status = "pending"
        reason = "waiting_real_pairs：真实配对未到位，标注未开始"
    elif blocking:
        status = "blocked"
        reason = "存在阻断性标注质量问题，禁止宣布标注完成"
    elif not all_rows:
        status = "pending"
        reason = "waiting_external_annotation：尚未收到任何人工标注"
    elif review:
        status = "needs_review"
        reason = "存在需人工复核的标注质量问题（不阻断保存，但不得宣布完成）"
    elif incomplete:
        status = "in_progress"
        reason = "标注进行中：仍有缺失标注/未决仲裁（只登记不填补）"
    else:
        status = "complete"
        reason = "双人独立标注齐备且全部质量检查通过"

    return {
        "annotation_status": status,
        "status": status,
        "reason": reason,
        "reasons": blocking + review + incomplete,
        "blocking": blocking,
        "review": review,
        "incomplete": incomplete,
        "checks": checks,
        "counts": counts,
        "vocabulary": list(ANNOTATION_STATUSES),
    }
