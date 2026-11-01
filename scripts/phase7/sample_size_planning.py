# -*- coding: utf-8 -*-
"""P7-1：真实人岗配对样本规模规划（Scenario A/B/C）与查询组统计稳定性测算。

任务背景：既有方案为「300–600 个真实人岗配对、每份简历 10–12 个岗位、
简历组级 70/30 划分」。若只有 300 个配对，可能仅覆盖 25–30 个独立简历查询组，
盲测组数不足以支撑稳定统计分析（协议要求有效查询组 < 20 标记统计不稳定）。

本脚本给出三种规模方案的**规划测算**：
  * 真实简历数量 / 每份简历岗位数 / 总配对数；
  * 训练 / 验证 / 盲测查询组数（组级 70/30）；
  * 标注员工作量（含仲裁）；
  * `unjudgeable` 预估敏感性分析（多档比例下的有效配对与有效组数）；
  * 剔除重复后的有效规模；
  * 统计稳定性风险与最小可检测效应（MDE）。

**纪律**：全部数值是**假设性的规划测算**，不是已采集或已标注事实。
假设项一律标记 `ASSUMPTION`，真实数据到位后必须用实测值回填并复算。
输出：reports/phase7/sample-size-planning.{json,md}
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, report_path, write_json  # noqa: E402

Z_ALPHA_2 = 1.959963984540054   # 双侧 alpha=0.05
Z_POWER = 0.8416212335729143   # power=0.80
Z_SUM = Z_ALPHA_2 + Z_POWER    # 2.8016

#: 协议口径（phase7-eval-protocol-v1）
MIN_GROUPS_FOR_STABILITY = 20
DEV_RATIO = 0.70
BLIND_RATIO = 0.30
PAIRS_GATE_MIN = 300

#: 规划假设（ASSUMPTION，非实测）
ASSUMED_SD_DIFF = 0.20           # 配对差值标准差（NDCG@10 组级差值）
ASSUMED_UNJUDGEABLE_RATES = (0.05, 0.10, 0.20, 0.30)
ASSUMED_DEDUP_LOSS = 0.05        # 近重复/完全重复剔除损失
ASSUMED_DISAGREEMENT_RATE = 0.30  # 双人标注分歧率（需仲裁比例）
ASSUMED_MINUTES_PER_PAIR = 2.0   # 单个配对单人标注耗时
ASSUMED_ARBITRATION_MINUTES = 4.0  # 单个分歧仲裁耗时

SCENARIOS = (
    {
        "id": "A",
        "name": "最低配对门禁",
        "resume_count": 30,
        "pairs_per_resume": 10,
        "note": "对应既有 300 配对下限；仅用于流程跑通，不支撑稳定统计结论",
    },
    {
        "id": "B",
        "name": "具备合理独立查询组数",
        "resume_count": 70,
        "pairs_per_resume": 8,
        "note": "盲测查询组 ≥20，达到协议稳定性下限",
    },
    {
        "id": "C",
        "name": "具有更充分统计稳定性的扩展方案",
        "resume_count": 120,
        "pairs_per_resume": 10,
        "note": "突破既有 600 配对上限，用于把 MDE 压到 0.10 以内",
    },
)


def split_groups(total_groups: int) -> dict:
    """组级 70/30 划分（round-half-up，保证两侧行为确定）。"""
    blind = int(math.floor(total_groups * BLIND_RATIO + 0.5))
    blind = max(0, min(total_groups, blind))
    dev = total_groups - blind
    return {"dev_validation_groups": dev, "blind_test_groups": blind}


def mde(n_groups: int, sd_diff: float = ASSUMED_SD_DIFF) -> float | None:
    """最小可检测效应（paired bootstrap / 配对 t 近似，双侧 alpha=0.05, power=0.80）。"""
    if n_groups <= 0:
        return None
    return Z_SUM * sd_diff / math.sqrt(n_groups)


def required_groups(target_mde: float, sd_diff: float = ASSUMED_SD_DIFF) -> int:
    if target_mde <= 0:
        raise ValueError("target_mde 必须 > 0")
    return int(math.ceil((Z_SUM * sd_diff / target_mde) ** 2))


def plan_scenario(s: dict) -> dict:
    resumes = s["resume_count"]
    per = s["pairs_per_resume"]
    total_pairs = resumes * per
    groups = split_groups(resumes)

    dedup_kept = int(math.floor(total_pairs * (1 - ASSUMED_DEDUP_LOSS) + 0.5))
    dedup_loss = total_pairs - dedup_kept

    unjudgeable = []
    for rate in ASSUMED_UNJUDGEABLE_RATES:
        effective_pairs = int(math.floor(dedup_kept * (1 - rate) + 0.5))
        # 组仍保留，但组内可判定候选减少；用比例估计组级有效规模
        unjudgeable.append({
            "assumed_unjudgeable_rate": rate,
            "effective_judgeable_pairs": effective_pairs,
            "pairs_dropped_as_unjudgeable": dedup_kept - effective_pairs,
            "effective_pairs_per_resume": round(effective_pairs / resumes, 2) if resumes else 0.0,
            "risk": (
                "组内可判定候选 < 2 时该组退出排序指标分母（min_group_size_for_ranking=2）"
                if effective_pairs / max(1, resumes) < 2 else "可控"
            ),
        })

    annot_load = total_pairs * 2
    arbitrations = int(math.floor(total_pairs * ASSUMED_DISAGREEMENT_RATE + 0.5))
    hours_a = (total_pairs * ASSUMED_MINUTES_PER_PAIR) / 60.0
    hours_total = (annot_load * ASSUMED_MINUTES_PER_PAIR
                   + arbitrations * ASSUMED_ARBITRATION_MINUTES) / 60.0

    dev_mde = mde(groups["dev_validation_groups"])
    blind_mde = mde(groups["blind_test_groups"])
    blind_ok = groups["blind_test_groups"] >= MIN_GROUPS_FOR_STABILITY
    dev_ok = groups["dev_validation_groups"] >= MIN_GROUPS_FOR_STABILITY

    risks = []
    if total_pairs < PAIRS_GATE_MIN:
        risks.append(f"总配对 {total_pairs} < 协议最低门禁 {PAIRS_GATE_MIN}，H2 数据门禁 G1 不通过")
    if not blind_ok:
        risks.append(f"盲测查询组 {groups['blind_test_groups']} < {MIN_GROUPS_FOR_STABILITY}，"
                     "统计不稳定，禁止声明显著提升")
    if not dev_ok:
        risks.append(f"开发集查询组 {groups['dev_validation_groups']} < {MIN_GROUPS_FOR_STABILITY}，"
                     "选型只能是 provisional")
    if per < 2:
        risks.append("每份简历配对数 < 2，无法形成组内排序")
    if not risks:
        risks.append("无阻断性风险；仍需以实测 sd_diff 回填后复算 MDE")

    return {
        "scenario_id": s["id"],
        "scenario_name": s["name"],
        "note": s["note"],
        "inputs": {
            "real_resumes": resumes,
            "pairs_per_resume": per,
            "total_pairs": total_pairs,
            "split_method": "resume_id 组级划分",
            "dev_ratio": DEV_RATIO,
            "blind_ratio": BLIND_RATIO,
        },
        "query_group_split": groups,
        "post_dedup": {
            "assumed_dedup_loss_rate": ASSUMED_DEDUP_LOSS,
            "status": "ASSUMPTION",
            "effective_pairs": dedup_kept,
            "removed_pairs": dedup_loss,
        },
        "unjudgeable_sensitivity": unjudgeable,
        "annotation_workload": {
            "status": "ASSUMPTION",
            "annotators": 2,
            "labels_per_annotator": total_pairs,
            "total_labels": annot_load,
            "assumed_minutes_per_pair": ASSUMED_MINUTES_PER_PAIR,
            "assumed_disagreement_rate": ASSUMED_DISAGREEMENT_RATE,
            "assumed_arbitrations": arbitrations,
            "assumed_arbitration_minutes_each": ASSUMED_ARBITRATION_MINUTES,
            "hours_per_annotator": round(hours_a, 1),
            "hours_total_incl_arbitration": round(hours_total, 1),
        },
        "statistical_stability": {
            "min_groups_required": MIN_GROUPS_FOR_STABILITY,
            "dev_groups_stable": dev_ok,
            "blind_groups_stable": blind_ok,
            "mde_dev_validation": round(dev_mde, 4) if dev_mde else None,
            "mde_blind_test": round(blind_mde, 4) if blind_mde else None,
            "mde_formula": "MDE = (z_0.975 + z_0.80) * sd_diff / sqrt(n_groups)",
            "assumed_sd_diff": ASSUMED_SD_DIFF,
            "assumed_sd_diff_status": "ASSUMPTION（非实测；dev_validation 上实测后必须回填复算）",
            "interpretation": (
                "MDE 表示在当前组数下可稳定检出的 NDCG@10 最小差值；"
                "MDE 越小，能可靠判断的提升越细微"
            ),
        },
        "risk_summary": risks,
    }


def to_markdown(payload: dict) -> str:
    L = []
    L.append("# Phase7 样本规模规划（Scenario A/B/C）")
    L.append("")
    L.append(f"- 生成时间：{payload['generated_at']}")
    L.append(f"- 状态：`{payload['status']}` —— 全部为**假设性规划测算**，非已采集/已标注事实")
    L.append(f"- 协议：`{payload['protocol_id']}`（主指标 NDCG@10，paired bootstrap over 查询组）")
    L.append("")
    L.append("## 0. 口径与假设")
    L.append("")
    L.append("| 项 | 取值 | 状态 |")
    L.append("|---|---|---|")
    L.append(f"| 组级划分比例（dev / blind） | {DEV_RATIO:.0%} / {BLIND_RATIO:.0%} | 协议锁定 |")
    L.append(f"| 统计稳定性下限（有效查询组） | {MIN_GROUPS_FOR_STABILITY} | 协议锁定 |")
    L.append(f"| H2 配对最低门禁 | {PAIRS_GATE_MIN} | 协议锁定 |")
    L.append(f"| 配对差值标准差 sd_diff | {ASSUMED_SD_DIFF} | **ASSUMPTION** |")
    L.append(f"| unjudgeable 敏感性档位 | {', '.join(f'{r:.0%}' for r in ASSUMED_UNJUDGEABLE_RATES)} | **ASSUMPTION** |")
    L.append(f"| 去重剔除损失 | {ASSUMED_DEDUP_LOSS:.0%} | **ASSUMPTION** |")
    L.append(f"| 双人标注分歧率 | {ASSUMED_DISAGREEMENT_RATE:.0%} | **ASSUMPTION** |")
    L.append(f"| 单配对单人标注耗时 | {ASSUMED_MINUTES_PER_PAIR} 分钟 | **ASSUMPTION** |")
    L.append(f"| 单分歧仲裁耗时 | {ASSUMED_ARBITRATION_MINUTES} 分钟 | **ASSUMPTION** |")
    L.append("")
    L.append("## 1. 三种方案总览")
    L.append("")
    L.append("| 方案 | 真实简历 | 每简历岗位 | 总配对 | dev 组 | blind 组 | blind MDE | blind 稳定 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for s in payload["scenarios"]:
        i, g, st = s["inputs"], s["query_group_split"], s["statistical_stability"]
        L.append(
            f"| {s['scenario_id']} {s['scenario_name']} | {i['real_resumes']} | {i['pairs_per_resume']} "
            f"| {i['total_pairs']} | {g['dev_validation_groups']} | {g['blind_test_groups']} "
            f"| {st['mde_blind_test']} | {'是' if st['blind_groups_stable'] else '**否**'} |")
    L.append("")
    for s in payload["scenarios"]:
        i, g, st, w = s["inputs"], s["query_group_split"], s["statistical_stability"], s["annotation_workload"]
        L.append(f"## 2.{s['scenario_id']} Scenario {s['scenario_id']}：{s['scenario_name']}")
        L.append("")
        L.append(f"> {s['note']}")
        L.append("")
        L.append(f"- 真实简历数量：**{i['real_resumes']}**")
        L.append(f"- 每份简历对应岗位数：**{i['pairs_per_resume']}**")
        L.append(f"- 总配对数：**{i['total_pairs']}**")
        L.append(f"- 训练/验证/盲测查询组数：主评价无训练标签 → "
                 f"dev_validation **{g['dev_validation_groups']}** / blind_test **{g['blind_test_groups']}**"
                 f"（训练组数仅对 E07 有意义，当前 `BLOCKED`）")
        L.append(f"- 标注员工作量：每人 {w['labels_per_annotator']} 条（合计 {w['total_labels']} 条标签），"
                 f"预计 {w['hours_per_annotator']} 小时/人；含仲裁合计约 **{w['hours_total_incl_arbitration']} 小时**")
        L.append(f"- 剔除重复后有效规模：{s['post_dedup']['effective_pairs']} 条"
                 f"（假设去重损失 {ASSUMED_DEDUP_LOSS:.0%}）")
        L.append(f"- 统计稳定性：dev MDE={st['mde_dev_validation']}，blind MDE={st['mde_blind_test']}"
                 f"（假设 sd_diff={ASSUMED_SD_DIFF}）")
        L.append("")
        L.append("| unjudgeable 假设 | 有效可判定配对 | 丢弃为 unjudgeable | 每简历有效候选 | 风险 |")
        L.append("|---|---:|---:|---:|---|")
        for u in s["unjudgeable_sensitivity"]:
            L.append(f"| {u['assumed_unjudgeable_rate']:.0%} | {u['effective_judgeable_pairs']} "
                     f"| {u['pairs_dropped_as_unjudgeable']} | {u['effective_pairs_per_resume']} | {u['risk']} |")
        L.append("")
        L.append("风险登记：")
        for r in s["risk_summary"]:
            L.append(f"- {r}")
        L.append("")
    L.append("## 3. 结论（规划层）")
    L.append("")
    for line in payload["conclusions"]:
        L.append(f"- {line}")
    L.append("")
    L.append("## 4. 纪律声明")
    L.append("")
    for line in payload["discipline"]:
        L.append(f"- {line}")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase7 样本规模规划（假设性测算）")
    ap.add_argument("--write-report", action="store_true", default=True)
    args = ap.parse_args(argv)

    scenarios = [plan_scenario(s) for s in SCENARIOS]
    blind_stable = [s["scenario_id"] for s in scenarios if s["statistical_stability"]["blind_groups_stable"]]
    gate_pass = [s["scenario_id"] for s in scenarios if s["inputs"]["total_pairs"] >= PAIRS_GATE_MIN]

    # 反推所需查询组规模：blind 组数 ≥ 目标 → 总组数 = ceil(target / blind_ratio)
    blind_groups_needed = int(math.ceil(MIN_GROUPS_FOR_STABILITY / BLIND_RATIO))
    blind_groups_for_mde10 = int(math.ceil(required_groups(0.10) / BLIND_RATIO))

    conclusions = [
        f"Scenario A（30 简历 × 10 岗 = 300 配对）只覆盖 30 个查询组，组级 70/30 后盲测组数为 "
        f"{scenarios[0]['query_group_split']['blind_test_groups']}，低于稳定性下限 "
        f"{MIN_GROUPS_FOR_STABILITY}，**不能支撑稳定统计结论**——这正是任务书指出的风险。",
        f"达到「盲测有效查询组 ≥ {MIN_GROUPS_FOR_STABILITY}」需要至少 "
        f"{blind_groups_needed} 个独立查询组（blind 占 {BLIND_RATIO:.0%} → "
        f"ceil({MIN_GROUPS_FOR_STABILITY}/{BLIND_RATIO:.2f}) = {blind_groups_needed}），"
        f"按每份简历 8–12 个岗位计，约需 {blind_groups_needed * 8}–{blind_groups_needed * 12} 个配对。",
        f"若目标是 blind MDE ≤ 0.10（NDCG@10，假设 sd_diff={ASSUMED_SD_DIFF}），需要约 "
        f"{required_groups(0.10)} 个盲测查询组，即约 {blind_groups_for_mde10} 个独立查询组，"
        f"对应 Scenario C 量级（{scenarios[2]['inputs']['real_resumes']} 份简历 / "
        f"{scenarios[2]['inputs']['total_pairs']} 配对）。",
        f"满足配对门禁的方案：{', '.join(gate_pass) or '无'}；满足盲测统计稳定性的方案："
        f"{', '.join(blind_stable) or '无'}。",
        "Scenario A 仅可作为「流程与工具链跑通」的最小可行规模；正式结论必须至少采用 Scenario B。",
    ]

    payload = {
        "artifact": "phase7-sample-size-planning",
        "status": "PLANNING_ASSUMPTIONS_NOT_COLLECTED_FACTS",
        "generated_at": "2026-10-31T22:20:00+08:00",
        "protocol_id": "phase7-eval-protocol-v1",
        "method": {
            "split": f"resume_id 组级 {int(DEV_RATIO*100)}/{int(BLIND_RATIO*100)}",
            "mde_formula": "MDE = (z_0.975 + z_0.80) * sd_diff / sqrt(n_groups)",
            "z_sum": round(Z_SUM, 6),
            "assumed_sd_diff": ASSUMED_SD_DIFF,
        },
        "scenarios": scenarios,
        "required_groups_for_target_mde": {
            "mde_0.20": required_groups(0.20),
            "mde_0.15": required_groups(0.15),
            "mde_0.10": required_groups(0.10),
            "mde_0.05": required_groups(0.05),
        },
        "total_query_groups_needed": {
            "for_blind_groups_ge_20": blind_groups_needed,
            "for_blind_mde_le_0.10": blind_groups_for_mde10,
            "formula": "total_groups = ceil(target_blind_groups / blind_ratio)",
            "blind_ratio": BLIND_RATIO,
        },
        "conclusions": conclusions,
        "discipline": [
            "以上全部为规划测算，不是已采集或已标注事实",
            "不得把假设值写成实测值；真实数据到位后必须用实测 sd_diff / unjudgeable 率回填并复算",
            "不得为凑够规模而降低授权、中文准入或双人标注门禁",
            "不得通过删除低质量样本提高指标；unjudgeable 必须保留并单独统计",
        ],
    }

    json_path = write_json(report_path("reports", "phase7", "sample-size-planning.json"), payload)
    md_path = report_path("reports", "phase7", "sample-size-planning.md")
    md_path.write_text(to_markdown(payload), encoding="utf-8")
    print(f"[OK] 样本规模规划已写出:\n  {json_path}\n  {md_path}")
    for line in conclusions:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
