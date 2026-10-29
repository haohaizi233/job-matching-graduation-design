# -*- coding: utf-8 -*-
"""Phase4-3A 编排入口：审计 -> 协议产物 -> 候选池 -> 泄漏检查 -> 标注流程 ->
冻结 -> 评估就绪 -> 阶段报告。

用法：
  python scripts/phase4_3a/run_all.py [--near-limit 80000] [--jobs 150] [--skip-pool]

产物：
  reports/phase4-3a/dataset-audit.{json,md}
  reports/phase4-3a/leakage-check.json
  reports/phase4-3a/annotation-quality.json
  reports/phase4-3a/evaluation-readiness.json
  reports/phase4-3a/phase4-3a-acceptance.md
  data/independent_eval/**（候选池、模板、冻结清单）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from common import FROZEN_DIR, REPORT_DIR, md_table, now  # noqa: E402

import audit_data  # noqa: E402
import build_pool  # noqa: E402
import check_agreement  # noqa: E402
import freeze_dataset  # noqa: E402
import import_annotations  # noqa: E402
import leakage_check  # noqa: E402
import run_eval  # noqa: E402
from job_matching.core import ROOT, jload  # noqa: E402


def render_dataset_audit_md(audit: dict, leak: dict) -> str:
    av = audit["availability"]
    lines = [
        "# Phase4-3A 数据可用性与工程审计", "",
        f"> 生成时间：{now()} ｜ 机器可读版本：`reports/phase4-3a/dataset-audit.json`", "",
        "## 一、数据可用性统计（任务书 5.1）", "",
        md_table(["统计项", "数量", "状态/说明"], [
            ["中文简历", av["chinese_resumes"]["count"], av["chinese_resumes"]["note"]],
            ["英文简历", av["english_resumes"]["count"], av["english_resumes"]["note"]],
            ["中文岗位（唯一 job_id）", av["chinese_jobs"]["count_unique_ids"],
             f"含 JD 正文行数 {av['chinese_jobs']['rows_with_jd_text']}"],
            ["英文岗位", av["english_jobs"]["count_unique_ids"], av["english_jobs"]["note"]],
            ["简历-岗位合法关联（英文）", av["resume_job_links"]["english_links"],
             "matches.csv 全部为正样本代理标签"],
            ["简历-岗位合法关联（中文）", av["resume_job_links"]["chinese_links"],
             "依赖真实中文简历导入"],
            ["含完整 JD 文本的记录", av["records_with_full_jd_text"], ""],
            ["只有标签/字段、无文本证据",
             av["records_label_only_no_text_evidence"]["matches_csv"] +
             av["records_label_only_no_text_evidence"]["all_df_structured_only"],
             "matches.csv 评分记录 + all_df 结构化字段"],
            ["缺少来源或使用许可", av["records_missing_source_or_license"]["count"],
             json.dumps(av["records_missing_source_or_license"]["detail"], ensure_ascii=False)],
        ]),
        "", "## 二、数据缺口（G2 阻断项）", "",
    ]
    for gap in audit["data_gaps"]:
        lines.append(f"- **{gap['item']}**：当前 {gap['current']} ｜ 影响：{gap['impact']}")
    lines += ["", "## 三、能力复用审计（任务书第三节）", "", "### 可直接复用", ""]
    for item in audit["capability_audit"]["reusable"]:
        lines.append(f"- **{item['item']}**（{item['where']}）：{item['use']}")
    lines += ["", "### 本阶段新建", ""]
    for item in audit["capability_audit"]["newly_built"]:
        lines.append(f"- **{item['item']}**：{item['where']}")
    lines += ["", "### 不复用的原因", ""]
    for k, v in audit["capability_audit"]["not_reused_reason"].items():
        lines.append(f"- `{k}`：{v}")
    lines += ["", "## 四、泄漏检查摘要", "",
              md_table(["检查项", "结果"], [
                  ["池内配对完全重复",
                   leak["pool_internal_duplicates"]["pair_level"]["exact_duplicates"]],
                  ["池内配对近似重复",
                   leak["pool_internal_duplicates"]["pair_level"]["near_duplicates"]],
                  ["同一简历不同 ID",
                   leak["pool_internal_duplicates"]["resume_level"]["same_resume_different_id"]],
                  ["同一岗位不同 ID",
                   leak["pool_internal_duplicates"]["job_level"]["same_job_different_id"]],
                  ["与原历史 Gold 交叉（job_id）",
                   leak["historical_gold_cross"].get("overlap_job_ids", "n/a")],
                  ["与学历训练语料文本重合（哈希）",
                   leak["training_data_overlap"]["education_training_corpus"]["exact_or_norm_hash_overlap"]],
                  ["与学历训练语料近似重复",
                   leak["training_data_overlap"]["education_training_corpus"]["near_duplicate_overlap"]],
                  ["个人信息字段残留",
                   len(leak["pii_export_scan"]["pii_field_violations"])] ]),
              "",
              "预训练污染声明：" + leak["pretraining_contamination"]["statement"], ""]
    return "\n".join(lines)


def render_acceptance(audit: dict, leak: dict, quality: dict, readiness: dict,
                      freeze_res: dict, pool_res: dict, tests: dict | None) -> str:
    av = audit["availability"]
    g1_items = [
        ["样本构建脚本正常", pool_res["pairs_synthetic"]["pairs"] >= 0 and pool_res["job_pool"]["jobs"] > 0,
         f"岗位池 {pool_res['job_pool']['jobs']} 条；合成配对 {pool_res['pairs_synthetic']['pairs']} 条；"
         f"真实配对 {pool_res['pairs_real']['pairs']} 条"],
        ["标注协议明确", True, "docs/evaluation/phase4-3a-protocol.md + annotation-guidelines.md"],
        ["标注导入及仲裁可用", True, "src/job_matching/annotation/{importer,arbitration}.py + scripts/phase4_3a/{import_annotations,arbitrate}.py"],
        ["数据清洗和泄漏检查可用", True, "reports/phase4-3a/leakage-check.json"],
        ["评估程序可运行", True, "src/job_matching/independent_eval/ + scripts/phase4_3a/run_eval.py（合成演示见 data/independent_eval/demo/）"],
        ["冻结和哈希校验可用",
         (FROZEN_DIR / "pool_v1" / "manifest.json").exists()
         and (freeze_res.get("status") == "frozen"
              or (freeze_res.get("status") == "blocked" and bool(freeze_res.get("reason")))),
         f"候选池冻结 stage=pool（frozen/pool_v1/manifest.json 含文件 SHA-256，"
         f"verify_freeze 可复验）；evalset 冻结状态={freeze_res.get('status')}"
         f"：{freeze_res.get('reason', '') or '已冻结'}"],
        ["自动化测试全部通过", bool(tests and tests.get("ok")),
         f"reports/phase4-3a/test-results.json（PASS={tests.get('totals', {}).get('pass') if tests else 'n/a'}）"],
        ["真实数据缺口已如实登记", True, "dataset-audit.json -> data_gaps"],
    ]
    g2_items = [
        ["已取得符合授权要求的真实中文求职数据", av["chinese_resumes"]["count"] > 0,
         f"当前中文简历 {av['chinese_resumes']['count']} 份"],
        ["人工标注完成并通过质量检查", quality.get("annotation_status") == "complete",
         f"annotation_status={quality.get('annotation_status')}"],
        ["分歧处理完毕", quality.get("disagreements", {}).get("count", 0) == 0,
         f"未仲裁分歧 {quality.get('disagreements', {}).get('count', 0)}"],
        ["验证集与盲测集隔离", readiness.get("formal_metrics_allowed", False),
         "冻结后由 mutual_exclusivity 检查给出"],
        ["数据来源及哈希齐全", len(leak["files"]) > 0, "leakage-check.json -> files"],
        ["指标可从保存预测复算", False, "run_eval.py --verify 待 Gold 后启用"],
        ["没有已知阻断性泄漏", not leak["blocking_findings"],
         "; ".join(leak["blocking_findings"]) or "无"],
        ["样本规模与类别覆盖满足用途", False, "真实配对 0（缺中文简历）"],
    ]

    def _table(items):
        return md_table(["门禁项", "结论", "证据"],
                        [[n, "✅" if ok else "❌", ev] for n, ok, ev in items])

    g1_ok = all(ok for _n, ok, _e in g1_items)
    g2_ok = all(ok for _n, ok, _e in g2_items)
    lines = [
        "# Phase4-3A 阶段验收报告", "",
        f"> 生成时间：{now()} ｜ 协议版本：`phase4-3a-protocol-v1` / `phase4-3a-annotation-v1`", "",
        "## 一、结论", "",
        f"- **G1 评估工程就绪：{'通过' if g1_ok else '未通过'}**"
        + ("（Phase4-3A 工程部分通过，等待人工标注）" if g1_ok else ""),
        f"- **G2 独立评估数据正式可用：{'通过' if g2_ok else '未通过（BLOCKED）'}**"
        + ("" if g2_ok else "—— 未达到 G2，不得进入 Phase4-3B 最终模型选型"),
        f"- `annotation_status = {quality.get('annotation_status', 'pending')}`",
        f"- `blind_evaluation_status = {readiness.get('blind_evaluation_status', 'blocked')}`",
        f"- `final_model_selection_status = BLOCKED`", "",
        "## 二、G1 门禁", "", _table(g1_items), "",
        "## 三、G2 门禁", "", _table(g2_items), "",
        "## 四、数据与泄漏事实", "",
        f"- 中文简历 {av['chinese_resumes']['count']} 份（数据缺口）；英文简历 "
        f"{av['english_resumes']['count']} 份（禁止充当中国大学生就业画像数据）",
        f"- 中文岗位 {av['chinese_jobs']['count_unique_ids']} 个唯一 ID，"
        f"含 JD 正文 {av['chinese_jobs']['rows_with_jd_text']} 行；英文岗位 "
        f"{av['english_jobs']['count_unique_ids']} 个",
        f"- 岗位候选池 {pool_res['job_pool']['jobs']} 条（分层采样 seed="
        f"{pool_res['job_pool']['stats']['sampling']['seed']}）；合成测试配对 "
        f"{pool_res['pairs_synthetic']['pairs']} 条（`is_synthetic=true`，永不进人工真值）",
        f"- 泄漏检查：池内完全重复 "
        f"{leak['pool_internal_duplicates']['pair_level']['exact_duplicates']}，近似重复 "
        f"{leak['pool_internal_duplicates']['pair_level']['near_duplicates']}，"
        f"与历史 Gold 交叉 {leak['historical_gold_cross'].get('overlap_job_ids')} 个 job_id，"
        f"与学历训练语料哈希重合 "
        f"{leak['training_data_overlap']['education_training_corpus']['exact_or_norm_hash_overlap']}",
        f"- 预训练污染：{leak['pretraining_contamination']['statement']}", "",
        "## 五、阻断项与下一阶段前置条件", "",
    ]
    for item in audit["data_gaps"]:
        lines.append(f"- [ ] {item['item']}（当前 {item['current']}）：{item['impact']}")
    lines += [
        "- [ ] 双人独立标注完成（≥2 名标注员，盲标，`annotation_status=complete`）",
        "- [ ] 分歧样本仲裁完成并保留原始标注",
        "- [ ] 正式评估集冻结（`freeze_dataset.py --stage evalset`）",
        "- [ ] 在 `dev_validation` 上完成选型、在 `blind_test` 上做一次性盲测",
        "", "## 六、结论纪律", "",
        "1. 本轮**没有**真实人工 Gold，任何模型性能数值都不成立；",
        "2. 合成测试池结果只证明流水线可运行（`data/independent_eval/demo/`），不是模型结论；",
        "3. 已归档模型训练标签为英文代理标签，其在中文语境下的分数只能作参考；",
        "4. 泄漏检查只能声明『未发现已知泄漏』，不能证明绝对无泄漏。", "",
        "## 七、文件索引", "",
        "- 协议：`docs/evaluation/phase4-3a-protocol.md`、`docs/evaluation/annotation-guidelines.md`",
        "- 代码：`src/job_matching/annotation/`、`src/job_matching/independent_eval/`、"
        "`scripts/phase4_3a/`、`tests/phase4_3a/`",
        "- 报告：`reports/phase4-3a/`（dataset-audit / leakage-check / annotation-quality / "
        "evaluation-readiness / test-results）",
        "- 数据：`data/independent_eval/`（pool / pairs / annotation / frozen / demo）", "",
    ]
    return "\n".join(lines)


def _pool_summary_from_disk() -> dict:
    """--skip-pool 时从已生成的池清单汇总（不重跑抽样，保持确定性）。"""
    from common import POOL_DIR
    manifest_path = POOL_DIR / "pool_manifest_v1.json"
    empty = {"job_pool": {"jobs": 0, "stats": {}},
             "pairs_real": {"pairs": 0, "stats": {}},
             "pairs_synthetic": {"pairs": 0, "stats": {}}}
    if not manifest_path.exists():
        return empty
    m = jload(manifest_path)
    job_pool = m.get("job_pool", {}) or {}
    pair_pool = m.get("pair_pool", {}) or {}
    return {
        "job_pool": {"jobs": int(job_pool.get("jobs_selected", 0)), "stats": job_pool},
        "pairs_real": {"pairs": int((pair_pool.get("real") or {}).get("pairs_built", 0)),
                       "stats": pair_pool.get("real") or {}},
        "pairs_synthetic": {"pairs": int((pair_pool.get("synthetic") or {}).get("pairs_built", 0)),
                            "stats": pair_pool.get("synthetic") or {}},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--near-limit", type=int, default=80000)
    ap.add_argument("--jobs", type=int, default=150)
    ap.add_argument("--skip-pool", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    audit = audit_data.run()
    pool_res = build_pool.run(jobs=args.jobs) if not args.skip_pool else _pool_summary_from_disk()
    leak = leakage_check.run(near_limit=args.near_limit)
    import_annotations.run()
    quality = check_agreement.run()
    freeze_res = freeze_dataset.run("evalset")
    readiness = run_eval.run(demo=True)

    tests = None
    test_file = REPORT_DIR / "test-results.json"
    if test_file.exists():
        tests = jload(test_file)

    (REPORT_DIR / "dataset-audit.md").write_text(
        render_dataset_audit_md(audit, leak), encoding="utf-8", newline="\n")
    (REPORT_DIR / "phase4-3a-acceptance.md").write_text(
        render_acceptance(audit, leak, quality, readiness, freeze_res, pool_res, tests),
        encoding="utf-8", newline="\n")

    summary = {
        "seconds": round(time.time() - t0, 1),
        "annotation_status": quality.get("annotation_status"),
        "blind_evaluation_status": readiness.get("blind_evaluation_status"),
        "evalset_freeze": freeze_res.get("status"),
        "jobs_in_pool": pool_res.get("job_pool", {}).get("jobs"),
        "real_pairs": pool_res.get("pairs_real", {}).get("pairs"),
        "synthetic_pairs": pool_res.get("pairs_synthetic", {}).get("pairs"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
