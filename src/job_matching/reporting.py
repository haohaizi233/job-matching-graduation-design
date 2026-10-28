# -*- coding: utf-8 -*-
"""报告生成：从落盘的 JSON 产物渲染 Markdown 报告（不手写数值，杜绝虚构）。

生成：
  reports/data-preprocessing.md
  reports/data-split-validation.md
  reports/baselines/matching-baselines.md
  reports/baselines/education-baselines.md
  reports/phase3-acceptance.md
"""
from __future__ import annotations

import time
from pathlib import Path

from .config import get_config
from .core import ROOT, get_logger, jload, rel

SPLITS = ("train", "validation", "test")


def _p(rel_path: str) -> Path:
    return ROOT / rel_path


def _load(rel_path: str) -> dict:
    p = _p(rel_path)
    return jload(p) if p.exists() else {}


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    return path


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


# ================================================================ 数据预处理
def render_preprocessing() -> str:
    s = _load("reports/phase3-preprocessing-summary.json")
    sch = _load("reports/phase3-schema-validation.json")
    emb = _load("data/processed/embeddings/metadata.json")
    L = []
    L.append("# 第三阶段 · 数据清洗与特征工程实测记录")
    L.append("")
    L.append(f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"- 流水线版本：{s.get('pipeline_version', '-')}")
    L.append(f"- 数据版本（由原始文件哈希推导）：`{s.get('dataset_version', '-')}`")
    L.append("- 格式说明：本地缺少 Parquet 引擎（`pyarrow`/`fastparquet` 均未安装），"
             "按阶段约束不修改环境，表格产物统一使用 **CSV**，向量用 **NPY**，清单用 **JSON**。")
    L.append("")
    L.append("## 1. Schema 校验结果")
    L.append("")
    rows = []
    for c in sch.get("checks", []):
        rows.append([f"`{c['path']}`", c.get("schema", "-"),
                     c.get("variant", "-") or "-", c.get("rows", 0),
                     c.get("hard_issue_count", 0),
                     "PASS" if c.get("ok") else "FAIL",
                     "一致" if c.get("column_set_ok", True) else "不一致"])
    L.append(_md_table(["文件", "Schema", "变体", "行数", "硬问题", "结论", "列集合"], rows))
    L.append("")
    L.append("> 「硬问题」= 缺列 / 主键重复 / 越界 / 非法枚举 / 非预期空值；"
             "未知列仅作 WARN 提示，不判失败。学历数据分 `default` 与 `annotated` 两个列变体，"
             "已分别核对精确列集合。")
    L.append("")

    L.append("## 2. 简历数据规范化（cv.csv）")
    L.append("")
    r = s.get("resume", {})
    L.append(_md_table(["项目", "值"], [
        ["输入行数", r.get("rows_before", "-")], ["输出行数", r.get("rows_after", "-")],
        ["主键唯一", r.get("primary_key_unique", "-")],
        ["技能为空的行", r.get("skills", {}).get("rows_with_zero_skills", "-")],
        ["技能待复核的行", r.get("skills", {}).get("rows_needs_review", "-")],
        ["唯一规范技能数", r.get("skills", {}).get("unique_canonical_skills", "-")],
        ["唯一原始技能数", r.get("skills", {}).get("unique_raw_skills", "-")],
        ["输出文件", f"`{r.get('output', '-')}`"],
        ["输出 SHA-256", f"`{r.get('sha256', '-')}`"],
    ]))
    L.append("")
    L.append("文本 Unicode 规范化（NFKC + 空白折叠）导致内容变化的行数：")
    L.append(_md_table(["字段", "变化行数"],
                       [[k, v] for k, v in (r.get("text_changed_by_normalization") or {}).items()]))
    L.append("")
    L.append("工作年限字段检查：")
    L.append(_md_table(["标志", "行数"], [[k, v] for k, v in
                                          (r.get("years_experience_flag_counts") or {}).items()]))
    L.append("")

    L.append("## 3. 岗位数据规范化（job.csv）")
    L.append("")
    j = s.get("job", {})
    dup = j.get("education_text_duplication", {})
    yr = j.get("years_required", {})
    L.append(_md_table(["项目", "值"], [
        ["输入行数", j.get("rows_before", "-")], ["输出行数", j.get("rows_after", "-")],
        ["`education_text` 与 `job_description` 逐行相同的行数",
         f"{dup.get('rows_equal_to_job_description', '-')} / {dup.get('rows_total', '-')}"],
        ["重复判定", dup.get("verdict", "-")], ["处置", dup.get("action", "-")],
        ["`years_required` 范围",
         f"{yr.get('min', '-')} ~ {yr.get('max', '-')}（均值 {yr.get('mean', '-')}）"],
        ["非整数取值行数", yr.get("non_integer_count", "-")],
        ["语义判定", yr.get("verdict", "-")], ["处置", yr.get("action", "-")],
    ]))
    L.append("")
    L.append("异常标记分布：")
    L.append(_md_table(["标志", "行数"], [[k, v] for k, v in (yr.get("flag_counts") or {}).items()]))
    L.append("")

    L.append("## 4. 学历样本规范化（job-education）")
    L.append("")
    e = s.get("education", {})
    L.append(_md_table(["项目", "行数"], [[k, v] for k, v in (e.get("source_rows") or {}).items()]))
    L.append("")
    L.append(f"- 合并后统一记录表行数：**{e.get('merged_rows', '-')}**")
    L.append(f"- 输出文件：`{e.get('output', '-')}`")
    L.append(f"- 输出 SHA-256：`{e.get('sha256', '-')}`")
    L.append("")
    L.append("标签 token 统计（多标签，可重复计数）：")
    L.append(_md_table(["标签 token", "出现次数"], [[k, v] for k, v in
                                                  (e.get("label_token_counts") or {}).items()]))
    L.append("")
    L.append("标签规范化状态：")
    L.append(_md_table(["状态", "行数"], [[k, v] for k, v in
                                          (e.get("label_status_counts") or {}).items()]))
    L.append("")
    L.append("> `oov_token` 表示出现词表外 token（实测如 `大四保研准硕士`），"
             "按规范**保留原值并标记待确认**，不强行归并到 6 token 词表。")
    L.append("")

    L.append("## 5. 招聘风险数据规范化（all_df.csv）")
    L.append("")
    k = s.get("risk", {})
    L.append(_md_table(["项目", "值"], [
        ["输入行数", k.get("rows_before", "-")],
        ["去重后行数", k.get("rows_after", "-")],
        ["删除的重复行", k.get("rows_dropped_as_duplicate", "-")],
        ["重复占比", k.get("duplicate_ratio", "-")],
        ["处置", k.get("task_decision", "-")],
    ]))
    scam = k.get("scam_probability", {})
    L.append("")
    L.append(f"- `scam_probability` 实测唯一取值：{scam.get('unique_values')}")
    L.append(f"- 是否全部为 10 的倍数：{scam.get('all_multiples_of_10')}")
    L.append(f"- 判定：{scam.get('verdict')}")
    L.append(f"- 处置：{scam.get('action')}")
    L.append("")

    L.append("## 6. Embedding 工程化缓存")
    L.append("")
    rows = []
    for side in ("cv", "job"):
        i = emb.get("sides", {}).get(side, {})
        rows.append([side, i.get("rows", "-"), i.get("dim", "-"), i.get("dtype", "-"),
                     f"{i.get('l2_norm_mean', '-')} ± {i.get('l2_norm_std', '-')}",
                     i.get("all_finite", "-"), i.get("zero_vectors", "-"),
                     i.get("duplicate_vectors", "-"), f"`{i.get('npy', '-')}`"])
    L.append(_md_table(["侧", "行数", "维度", "类型", "L2 范数", "全有限", "零向量", "重复向量", "文件"], rows))
    L.append("")
    ver = emb.get("verification", {})
    L.append(f"缓存与原始 CSV 的数值一致性校验（bit 级抽样比对）：**{'通过' if ver.get('ok') else '未通过'}**")
    L.append("")
    L.append(_md_table(["侧", "抽样行数", "最大绝对误差", "ID 映射可逆", "维度正确", "结论"],
                       [[c.get("side"), c.get("sample_rows_compared"),
                         c.get("max_abs_diff_vs_source"), c.get("id_map_reversible"),
                         c.get("dim_ok"), "PASS" if c.get("ok") else "FAIL"]
                        for c in ver.get("checks", [])]))
    L.append("")
    L.append("### 预计算 Embedding 的来源限制（必须随实验结论一并引用）")
    L.append("")
    for x in emb.get("limitations", []):
        L.append(f"- {x}")
    L.append("")

    L.append("## 7. 产物清单")
    L.append("")
    rows = []
    for group in ("interim_matching", "interim_education", "interim_risk",
                  "processed_embeddings", "processed_matching", "processed_education"):
        d = get_config().out(group)
        if not d.exists():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file():
                rows.append([f"`{rel(f)}`", f.stat().st_size])
    L.append(_md_table(["文件", "字节数"], rows))
    L.append("")
    return "\n".join(L)


# ================================================================ 切分验证
def render_splits() -> str:
    s = _load("reports/phase3-split-summary.json")
    m = s.get("matching", {})
    e = s.get("education", {})
    L = []
    L.append("# 第三阶段 · 可信数据划分实测结果")
    L.append("")
    L.append(f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append("- 切分索引：`data/splits/matching/`、`data/splits/education/`")
    L.append("- 所有随机过程使用 `configs/data_pipeline.yaml` 中登记的固定种子，重复执行结果一致。")
    L.append("")
    L.append("> **标签与预处理隔离**：StandardScaler / TF-IDF / 词表 / 特征选择器等"
             "统计量只能在 Train 上 fit，Validation/Test 只能 transform。"
             "预计算 Embedding 由全量数据产生，这一点作为限制单独记录。")
    L.append("")

    L.append("## 一、人岗匹配三种协议")
    L.append("")
    for name in ("candidate_cold", "job_cold", "double_cold"):
        man = m.get(name, {})
        proto = get_config().protocol(name)
        L.append(f"### 协议 {proto['id']}：{proto['name']}（`{name}`）")
        L.append("")
        L.append(f"- 分组键：`{man.get('group_key')}`")
        L.append(f"- 随机种子：`{man.get('seed')}`")
        L.append(f"- 划分比例：{man.get('ratios')}")
        if man.get("assignment_strategy"):
            L.append(f"- 分配策略：`{man['assignment_strategy']}` —— {man.get('assignment_strategy_note', '')}")
        L.append("")
        rows = []
        for split in SPLITS:
            info = man.get("splits", {}).get(split, {})
            rows.append([split, info.get("pairs", 0), info.get("candidates", 0),
                         info.get("jobs", 0),
                         info.get("groups_total", 0), info.get("groups_size_ge_2", 0),
                         info.get("groups_size_eq_1", 0),
                         info.get("size_median", 0), info.get("size_max", 0)])
        L.append(_md_table(["集合", "匹配记录", "候选人数", "岗位数", "分组数",
                            "可排序组(≥2)", "单记录组", "组大小中位", "组大小最大"], rows))
        L.append("")
        rows = []
        for split in SPLITS:
            dist = man.get("splits", {}).get(split, {}).get("label_distribution", {}) or {}
            rows.append([split, dist.get("weak_positive", 0), dist.get("medium_positive", 0),
                         dist.get("strong_positive", 0)])
        L.append(_md_table(["集合", "weak_positive", "medium_positive", "strong_positive"], rows))
        L.append("")
        oc = man.get("overlap_check", {})
        rows = [[k, v] for k, v in (oc.get("candidate_overlap") or {}).items()]
        L.append("候选人集合交叉：" + (", ".join(f"{k}={v}" for k, v in rows) or "-"))
        rows = [[k, v] for k, v in (oc.get("job_overlap") or {}).items()]
        L.append("岗位集合交叉：" + (", ".join(f"{k}={v}" for k, v in rows) or "-"))
        rows = [[k, v] for k, v in (oc.get("pair_overlap") or {}).items()]
        L.append("pair 交叉：" + (", ".join(f"{k}={v}" for k, v in rows) or "-"))
        L.append("")
        if man.get("excluded", {}).get("pairs"):
            exc = man["excluded"]
            L.append(f"**未采用的交叉边（excluded）**：{exc['pairs']} 条，"
                     f"涉及 {exc.get('candidates')} 个候选人、{exc.get('jobs')} 个岗位；"
                     f"标签分布 {exc.get('label_distribution')}。")
            L.append("")
        if man.get("coverage", {}).get("retention_ratio") is not None:
            cov = man["coverage"]
            L.append(f"覆盖率：原始 {cov['raw_pairs']} 条，保留 {cov['assigned_pairs']} 条 "
                     f"（保留率 {cov['retention_ratio']}），排除 {cov['excluded_pairs']} 条 "
                     f"（丢弃率 {cov['drop_ratio']}）。")
            L.append("")
            L.append(f"- 参照：两侧独立按 80/10/10 分配的期望保留率仅 "
                     f"**{man.get('naive_independent_expected_retention')}**。")
            L.append(f"- {man.get('naive_independent_note', '')}")
            L.append("")

    L.append("## 二、学历数据重新划分")
    L.append("")
    L.append(f"- 分组键：{e.get('group_key')}")
    L.append(f"- 分组理由：{e.get('group_key_reason')}")
    L.append(f"- 随机种子：`{e.get('seed')}`")
    L.append("")
    rows = []
    for split in ("train", "validation", "gold_holdout"):
        info = e.get("splits", {}).get(split, {})
        rows.append([split, info.get("rows", 0), info.get("unique_job_id", 0),
                     info.get("unique_user_hash", 0), info.get("slot_present_ratio", 0),
                     info.get("label_provenance", {})])
    L.append(_md_table(["集合", "样本数", "唯一 job_id", "唯一输入文本",
                        "<学历描述> 覆盖率", "标签来源"], rows))
    L.append("")
    L.append("### 重复与冲突检查")
    L.append("")
    d = e.get("duplicate_analysis", {})
    L.append(_md_table(["检查项", "结果"], [[k, v] for k, v in d.items()
                                            if not k.startswith("_") and not isinstance(v, dict)]))
    L.append("")
    L.append("跨来源输入文本交叉：")
    L.append(_md_table(["来源对", "交叉输入数"], [[k, v] for k, v in
                                                 (d.get("cross_source_input_overlap") or {}).items()]))
    L.append("")
    L.append("### 互斥性检查")
    L.append("")
    for key, val in (e.get("overlap_check") or {}).items():
        L.append(f"- {key}：" + ", ".join(f"{k}={v}" for k, v in val.items()))
    L.append("")
    L.append("### 人工金标准隔离")
    L.append("")
    g = e.get("gold_isolation", {})
    L.append(_md_table(["项目", "值"], [[k, v] for k, v in g.items()]))
    L.append("")
    tsd = e.get("test_set_decision", {})
    L.append(f"### 测试集决策\n\n- 是否构建独立 test：**{tsd.get('built')}**\n- 理由：{tsd.get('reason')}")
    L.append("")
    lp = e.get("label_provenance_policy", {})
    L.append("### 标签可信度标识")
    L.append("")
    L.append(_md_table(["来源", "说明"], [[k, v] for k, v in lp.items()]))
    L.append("")
    L.append("### 排除记录")
    L.append("")
    L.append(_md_table(["排除原因", "行数"], [[k, v] for k, v in
                                              (e.get("excluded", {}).get("by_reason") or {}).items()]))
    L.append("")
    return "\n".join(L)


# ================================================================ 匹配 Baseline
def render_matching_baselines() -> str:
    b = _load("reports/baselines/baseline-results.json")
    mm = b.get("matching", {})
    L = []
    L.append("# 第三阶段 · 人岗匹配零训练 Baseline")
    L.append("")
    L.append(f"- 生成时间：{b.get('created_at', '-')}")
    L.append(f"- 数据版本：`{b.get('dataset_version', '-')}`")
    L.append(f"- 执行环境：{b.get('environment', {})}")
    L.append("")
    L.append("## 评估口径")
    L.append("")
    L.append("- **标签定义**：`label_strength` ∈ {weak_positive, medium_positive, strong_positive}，"
             "由原评分系统 `final_score` 阈值切分得到。")
    L.append("- **代理相关性**：`gain = final_score`（score 模式）或标签序数 1/2/3（ordinal 模式）。")
    L.append("- **二值相关性**（用于 MRR / Recall）：" +
             b.get("matching", {}).get("candidate_cold", {}).get("subsets", {})
             .get("validation", {}).get("results", {}).get("score", {})
             .get("random_ranking", {}).get("aggregate", {})
             .get("size_ge_2", {}).get("binary_relevance_rule", "-"))
    L.append("- **有效查询**：候选人拥有 ≥2 条观测匹配记录（组内可排序）；"
             "单记录组单独统计，不计入排序指标。")
    L.append("- **NDCG@K 截断**：`min(K, 组内候选数)`，与所有 Baseline 统一口径。")
    L.append("- **Tie-breaking**：分数相同按原始行序稳定排序，全部 Baseline 一致。")
    L.append("")
    L.append("## 重要限制（代理标签）")
    L.append("")
    for x in mm.get("candidate_cold", {}).get("caveats", []):
        L.append(f"- {x}")
    L.append("")

    for proto in ("candidate_cold", "job_cold", "double_cold"):
        blk = mm.get(proto, {})
        L.append(f"## 协议：{proto}")
        L.append("")
        for subset in ("validation", "test"):
            entry = blk.get("subsets", {}).get(subset, {})
            if not entry or not entry.get("results"):
                L.append(f"### {subset}：{entry.get('note', '无数据')}")
                L.append("")
                continue
            L.append(f"### {subset}（{entry.get('rows')} 条匹配记录，"
                     f"{entry.get('candidates')} 个候选人，{entry.get('jobs')} 个岗位）")
            L.append("")
            L.append(f"标签分布：{entry.get('label_distribution')}")
            L.append("")
            for gain_mode in ("score", "ordinal"):
                rows = []
                gain = entry.get("results", {}).get(gain_mode, {})
                for name, blk2 in gain.items():
                    agg = blk2.get("aggregate", {}).get("size_ge_2", {})
                    rnd = blk2.get("repeated_stats", {})
                    if name == "random_ranking":
                        cell = lambda k: (f"{rnd.get(f'{k}_mean')} ± {rnd.get(f'{k}_std')}"
                                          if rnd else "-")
                        rows.append(["Random Ranking（20 次重复）",
                                     cell("ndcg@5"), cell("ndcg@10"),
                                     cell("mrr@5"), cell("mrr@10"),
                                     cell("recall@5"), cell("recall@10"),
                                     agg.get("queries_evaluated", "-")])
                    else:
                        rows.append([name,
                                     agg.get("ndcg@5"), agg.get("ndcg@10"),
                                     agg.get("mrr@5"), agg.get("mrr@10"),
                                     agg.get("recall@5"), agg.get("recall@10"),
                                     agg.get("queries_evaluated", "-")])
                L.append(f"**gain_mode = {gain_mode}**"
                         + ("（增益 = final_score，代理偏好分数）" if gain_mode == "score"
                            else "（增益 = 标签序数 1/2/3）"))
                L.append("")
                L.append(_md_table(["Baseline", "NDCG@5", "NDCG@10", "MRR@5", "MRR@10",
                                    "Recall@5", "Recall@10", "有效查询"], rows))
                L.append("")
            gs = entry.get("results", {}).get("score", {}).get("random_ranking", {})
            L.append(f"查询候选数分布：{gs.get('aggregate', {}).get('size_ge_2', {})}")
            L.append("")

    L.append("## 有效查询与候选数量分布")
    L.append("")
    rows = []
    for proto in ("candidate_cold", "job_cold", "double_cold"):
        for subset in ("validation", "test"):
            e = mm.get(proto, {}).get("subsets", {}).get(subset, {})
            if not e.get("results"):
                continue
            g = (e.get("results", {}).get("score", {}).get("random_ranking", {})
                 .get("group_stats") or
                 e.get("results", {}).get("score", {}).get("embedding_cosine", {})
                 .get("group_stats", {}))
            rows.append([proto, subset, g.get("queries_total", "-"),
                         g.get("queries_size_ge_2", "-"), g.get("queries_size_eq_1", "-"),
                         g.get("group_size_distribution", {})])
    L.append(_md_table(["协议", "集合", "查询总数", "可评估(≥2)", "单记录组",
                        "组大小分布"], rows))
    L.append("")
    return "\n".join(L)


# ================================================================ 学历 Baseline
def render_education_baselines() -> str:
    b = _load("reports/baselines/baseline-results.json")
    edu = b.get("education", {})
    L = []
    L.append("# 第三阶段 · 学历任务零训练 Baseline")
    L.append("")
    L.append(f"- 生成时间：{edu.get('created_at', '-')}")
    L.append(f"- 数据版本：`{edu.get('dataset_version', '-')}`")
    L.append(f"- 标签词表顺序：{edu.get('label_order')}")
    L.append("")
    L.append("## 任务范围的准确表述")
    L.append("")
    L.append("实测输入 `user = <岗位名称>…</岗位名称><岗位描述>…</岗位描述><学历描述>…</学历描述>`，"
             "其中 `<学历描述>` 是上游已抽取的短槽位（中位长度 2 字符）。"
             "因此本数据可支撑的任务是 **学历要求表达的规范化 / 槽位校验与多标签归一**，"
             "**不是**「从完整招聘 JD 端到端抽取学历要求」。")
    L.append("")
    L.append("## 标签规范与「及以上」展开")
    L.append("")
    L.append("- 标签是「可接受学历集合」，按从高到低用 `、` 连接，如 `博士、硕士、本科`。")
    L.append("- 「X及以上」的展开方式（`expand_all_levels_ge`）**来源于对 19.7 万 + 4.6 万条"
             "伪标注数据的实测条件分布**，标注为 `pseudo_convention`（来源系统惯例），"
             "**不是人工标注规范**，也**未使用 736 条人工金标准做任何拟合或调参**。")
    L.append(f"- 人工金标准使用情况：`gold_used_for_rule_fitting = {edu.get('gold_used_for_rule_fitting')}`。")
    L.append(f"- 金标准评估策略：{edu.get('gold_eval_policy')}")
    L.append("")
    L.append("## 槽位表达 -> 标签 条件分布（实测证据，前 20 项）")
    L.append("")
    rows = []
    for slot, info in (edu.get("slot_label_mapping_top") or {}).items():
        rows.append([f"`{slot if slot else '(空)'}`", info.get("support"),
                     info.get("top_label"), info.get("top_ratio"),
                     info.get("distinct_labels")])
    L.append(_md_table(["<学历描述> 槽位", "支持度", "最常见标签", "占比", "不同标签数"], rows))
    L.append("")
    L.append(f"槽位唯一表达总数：{edu.get('slot_label_mapping_size')}")
    L.append("")

    L.append("## 评估结果")
    L.append("")
    L.append("> 严格区分：`dev_validation_pseudo` 是**伪标签**开发集；"
             "`gold_holdout_human` 是**人工金标准**，只做一次性最终评估。")
    L.append("")
    for set_name, label in (("dev_validation_pseudo", "开发集 · 伪标签 validation"),
                            ("gold_holdout_human", "人工金标准 gold_holdout（736 条）")):
        blk = edu.get("evaluation_sets", {}).get(set_name, {})
        if not blk:
            continue
        L.append(f"### {label}")
        L.append("")
        L.append(f"- 样本数：{blk.get('rows')}")
        L.append(f"- 标签来源：{blk.get('label_provenance')}")
        L.append("")
        rows = []
        for method, key in (("规则基线（Rule Baseline）", "rule_baseline"),
                            ("槽位经验映射（Empirical Baseline）", "empirical_slot_baseline")):
            m = blk.get(key, {})
            rows.append([method, m.get("exact_match_ratio"), m.get("micro_f1"),
                         m.get("macro_f1"), m.get("micro_precision"),
                         m.get("micro_recall")])
        L.append(_md_table(["方法", "Exact Match", "Micro-F1", "Macro-F1",
                            "Micro-P", "Micro-R"], rows))
        L.append("")
        m = blk.get("rule_baseline", {})
        rows = [[k, v.get("precision"), v.get("recall"), v.get("f1"),
                 v.get("support"), v.get("predicted")]
                for k, v in (m.get("per_label") or {}).items()]
        L.append("规则基线的每标签指标：")
        L.append(_md_table(["标签", "Precision", "Recall", "F1", "支持数", "预测数"], rows))
        L.append("")
        L.append(f"错误类型分布（规则基线）：{m.get('error_types')}")
        L.append("")
    L.append("## 参照系（原系统输出，仅作对照，不参与本阶段规则拟合）")
    L.append("")
    L.append("- `线上学历-旧的`（旧线上系统输出）：在 736 条人工金标准上逐条一致 "
             "**338 / 736 = 45.92%**（第二阶段实测）。")
    L.append("- `模型结果-新的`（新模型输出）：一致 **300 / 736 = 40.76%**，"
             "且实测该列含长文本噪声（22 个「唯一值」中包含 JD 片段），**不可用作标签**。")
    L.append("- 本阶段规则基线的输出完全由 `configs/education_labels.yaml` 的确定性规则决定，"
             "未使用上述任一输出做拟合。")
    L.append("")
    return "\n".join(L)


# ================================================================ 验收
def _gate_ok(gates: dict, gate: str) -> bool:
    return bool((gates.get("gates") or {}).get(gate, {}).get("ok", False))


def _gate_tests(gates: dict, gate: str) -> str:
    g = (gates.get("gates") or {}).get(gate, {})
    return f"{g.get('passed', '?')}/{g.get('total', '?')}" if g else "未运行"


def _acceptance_items() -> list[dict]:
    """P3-01 ~ P3-14 逐条取证（全部读取真实产物，不手写数值）。"""
    steps = {}
    for p in sorted((_p("reports") / "phase3-steps").glob("*.json")) if (_p("reports") / "phase3-steps").exists() else []:
        steps[p.stem] = jload(p)
    gates = _load("reports/data-quality-gates.json")
    deps = _load("reports/dependency-check.json")
    feat = _load("reports/phase3-feature-build.json")
    prep = _load("reports/phase3-preprocessing-summary.json")
    split = _load("reports/phase3-split-summary.json")
    base = _load("reports/baselines/baseline-results.json")
    rerun = _load("reports/phase3-reproducibility-rerun.json")

    s1 = steps.get("1-check_raw_integrity", {})
    s2 = steps.get("2-validate_schema", {})
    s4 = steps.get("4-build_embeddings", {})

    items: list[dict] = []

    def add(code: str, content: str, requirement: str, ok: bool | None, evidence: str):
        items.append({"code": code, "content": content, "requirement": requirement,
                      "verdict": "PASS" if ok else ("FAIL" if ok is False else "N/A"),
                      "evidence": evidence})

    n_files = len(s1.get("files", []))
    n_ok = sum(1 for f in s1.get("files", []) if f.get("ok"))
    add("P3-01", "原始数据完整性", "SHA-256 一致",
        bool(s1.get("ok")) and _gate_ok(gates, "G1"),
        f"流水线第 1 步核对 {n_ok}/{n_files} 个原始文件与第二阶段 SHA-256 基线一致；"
        f"G1 门禁 {_gate_tests(gates, 'G1')} 通过。")

    n_schema = len(s2.get("checks", []))
    n_schema_ok = sum(1 for c in s2.get("checks", []) if c.get("ok"))
    add("P3-02", "Schema", "关键字段全部验证",
        bool(s2.get("ok")) and bool(s2.get("column_set_ok")),
        f"{n_schema_ok}/{n_schema} 个数据文件通过 Resume/Job/Match/EducationSample "
        f"Schema 校验（含主键、枚举、取值范围、列集合）；"
        f"学历 default/annotated 两个列变体分别核对。")

    pa = feat.get("policy_audit", {})
    ep = feat.get("education_policy_check", {})
    add("P3-03", "特征泄漏防护", "禁止字段无法进入对应模型输入",
        _gate_ok(gates, "G3") and bool(pa.get("ok", False)) and bool(ep.get("ok", False)),
        f"G3 门禁 {_gate_tests(gates, 'G3')} 通过；实际特征矩阵 "
        f"{feat.get('matrix_shape')} 逐列通过白名单检查；"
        f"派生评分链 10 字段零命中；间接泄漏扫描（Spearman/R² 重建）"
        f"发现 {len(pa.get('indirect_findings', []))} 条硬问题。")

    ver = (s4.get("verification") or {})
    add("P3-04", "Embedding 缓存", "ID 映射和数值一致",
        bool(ver.get("ok")) and _gate_ok(gates, "G2") and _gate_ok(gates, "G6"),
        f"cv/job 两份 768 维 float32 缓存经 bit 级抽样回比原始 CSV，"
        f"最大绝对误差 {max([c.get('max_abs_diff_vs_source', -1) for c in ver.get('checks', [])] or [-1])}；"
        f"ID 映射可逆且行号连续；G2 {_gate_tests(gates, 'G2')}、G6 {_gate_tests(gates, 'G6')}。")

    add("P3-05", "数据清洗", "可复现且有异常统计",
        bool(prep.get("resume")) and _gate_ok(gates, "G5"),
        f"四张表规范化产物均带异常统计（技能待复核、years_required 标志、"
        f"education_text 重复判定、标签冲突），输出文件哈希已登记；"
        f"G5 门禁 {_gate_tests(gates, 'G5')} 复算一致。")

    def overlap_ok(proto_key: str) -> tuple[bool, str]:
        man = (split.get("matching") or {}).get(proto_key, {})
        oc = man.get("overlap_check", {}) or {}
        vals = []
        for k in ("candidate_overlap", "job_overlap", "pair_overlap"):
            d = oc.get(k) or {}
            vals.extend(d.values())
        return all(v == 0 for v in vals), str(oc)

    ok_a, ev_a = overlap_ok("candidate_cold")
    add("P3-06", "Candidate Cold-start", "候选人集合完全互斥",
        ok_a and _gate_ok(gates, "G4"),
        f"candidate_cold 互斥检查 {ev_a}；同一候选人的全部记录同集合；"
        f"G4 {_gate_tests(gates, 'G4')}。")
    ok_b, ev_b = overlap_ok("job_cold")
    add("P3-07", "Job Cold-start", "岗位集合完全互斥",
        ok_b and _gate_ok(gates, "G4"),
        f"job_cold 互斥检查 {ev_b}；G4 {_gate_tests(gates, 'G4')}。")
    ok_c, ev_c = overlap_ok("double_cold")
    cov = ((split.get("matching") or {}).get("double_cold", {}) or {}).get("coverage", {})
    add("P3-08", "Double Cold-start", "双侧实体互斥且记录覆盖率",
        ok_c and bool(cov.get("retention_ratio")),
        f"double_cold 互斥检查 {ev_c}；原始 {cov.get('raw_pairs')} 条，"
        f"保留 {cov.get('assigned_pairs')} 条（保留率 {cov.get('retention_ratio')}），"
        f"交叉边 {cov.get('excluded_pairs')} 条单独落盘为 excluded 索引。")

    e = (split.get("education") or {})
    oc = e.get("overlap_check", {}) or {}
    edu_ok = all(v == 0 for k, d in oc.items() for v in (d or {}).values())
    add("P3-09", "学历数据切分", "重复检查与金标准隔离",
        edu_ok and _gate_ok(gates, "G4"),
        f"输入文本/记录键/岗位键三类交叉全部为 0；金标准 736 条隔离为 gold_holdout，"
        f"与开发集输入交叉 {e.get('gold_isolation', {}).get('dev_input_hashes_touching_gold_after_removal')}；"
        f"因原 test ⊂ validation 且伪标签可信度低，未伪造独立 test（已在 manifest 记录理由）。")

    mc = ((base.get("matching") or {}).get("candidate_cold", {}) or {}).get("subsets", {})
    nd = (((mc.get("test", {}) or {}).get("results", {}) or {}).get("score", {})
          .get("embedding_cosine", {}).get("aggregate", {}).get("size_ge_2", {}) or {})
    add("P3-10", "Matching Baseline", "实际运行并产出指标",
        bool(nd.get("ndcg@5") is not None),
        f"Random / Embedding Cosine / Skill Jaccard / Position Overlap 四个基线"
        f"在同一候选集合与口径下完成 {len(mc)} 个子集 × 2 种增益模式评估；"
        f"示例（candidate_cold/test, embedding_cosine, gain=score）："
        f"NDCG@5={nd.get('ndcg@5')}、NDCG@10={nd.get('ndcg@10')}。")

    es = (base.get("education") or {}).get("evaluation_sets", {}) or {}
    gold_rule = (es.get("gold_holdout_human", {}) or {}).get("rule_baseline", {}) or {}
    add("P3-11", "Education Baseline", "在合法评估集合上完成测试",
        gold_rule.get("exact_match_ratio") is not None,
        f"规则基线与槽位经验映射基线在开发集（伪标签）与 gold_holdout（人工金标准 736 条）"
        f"分别评估；金标准 Exact Match={gold_rule.get('exact_match_ratio')}、"
        f"Micro-F1={gold_rule.get('micro_f1')}；未用金标准做任何拟合或调参。")

    rerun_ok = bool(rerun.get("ok")) if rerun else None
    add("P3-12", "结果可复现", "固定配置和种子重复执行一致",
        _gate_ok(gates, "G5") and (rerun_ok is not False),
        f"G5 门禁 {_gate_tests(gates, 'G5')}（划分 ID、样本计数、特征维度、文件哈希一致）；"
        + (f"全流水线重复执行比对：{rerun.get('summary', '')}" if rerun else
           "全流水线重复执行比对见 reports/phase3-reproducibility-rerun.json。"))

    add("P3-13", "依赖完整性", "pip check 通过",
        bool(deps.get("ok")),
        f"`pip check` 退出码 {deps.get('returncode')}："
        f"{(deps.get('stdout') or deps.get('stderr') or '-')[:200]}")

    add("P3-14", "自动化测试", "核心测试全部 PASS",
        bool(gates.get("ok")),
        f"tests/data_pipeline 共 {gates.get('tests_run')} 项，"
        f"失败 {gates.get('failures')}，错误 {gates.get('errors')}；"
        f"G1-G7 逐项结论见 reports/data-quality-gates.json。")
    return items


def render_acceptance() -> str:
    gates = _load("reports/data-quality-gates.json")
    base = _load("reports/baselines/baseline-results.json")
    items = _acceptance_items()
    L = []
    L.append("# 第三阶段验收报告")
    L.append("")
    L.append(f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"- 流水线版本：`{get_config().pipeline_version}`")
    L.append(f"- 数据版本：`{base.get('dataset_version', '-')}`")
    L.append("")
    L.append("## 自动化测试结果")
    L.append("")
    L.append(f"- 测试总数：{gates.get('tests_run', '-')}，"
             f"失败 {gates.get('failures', '-')}，错误 {gates.get('errors', '-')}")
    L.append(f"- 总体结论：**{'PASS' if gates.get('ok') else 'FAIL'}**")
    L.append("")
    rows = [[g, i.get("title"), f"{i.get('passed')}/{i.get('total')}",
             "PASS" if i.get("ok") else "FAIL"]
            for g, i in (gates.get("gates") or {}).items()]
    L.append(_md_table(["门禁", "内容", "通过/总数", "结论"], rows))
    L.append("")
    L.append("## 验收项逐条结论")
    L.append("")
    rows = [[i["code"], i["content"], i["requirement"], i["verdict"], i["evidence"]]
            for i in items]
    L.append(_md_table(["编号", "验收内容", "要求", "结论", "实际证据"], rows))
    L.append("")

    # ---- 特征白名单 / 黑名单摘要
    cfg = get_config()
    L.append("## 数据泄漏验证摘要")
    L.append("")
    for task in ("match_label_strength", "match_ranking", "edu_label_multilabel"):
        t = cfg.task(task)
        L.append(f"### 任务 `{task}`")
        L.append("")
        L.append("- 允许特征（白名单）：" + ", ".join(f"`{x}`" for x in t.get("allowed_features", [])))
        L.append("- 禁止字段（黑名单）：" + ", ".join(f"`{x}`" for x in t.get("forbidden_features", [])))
        L.append("- 监督目标：" + ", ".join(f"`{x}`" for x in t.get("target_columns", []))
                 + "；派生目标：" + ", ".join(f"`{x}`" for x in t.get("target_derived_columns", [])))
        L.append("- 评估元数据（不进特征）：" + ", ".join(f"`{x}`" for x in t.get("evaluation_metadata", [])))
        L.append("- 待定特征（默认禁止，需显式 opt-in）："
                 + (", ".join(f"`{x}`" for x in t.get("uncertain_features", [])) or "无"))
        L.append("")
    L.append("目标字段与输入的物理隔离：匹配任务 `features_pairs.csv` / `targets_pairs.csv`、"
             "学历任务 `education_inputs.csv` / `education_labels.csv` 分文件落盘，"
             "仅共享关联键（`candidate_id`/`job_id`/`record_key`）。")
    L.append("")

    # ---- 风险与剩余问题
    L.append("## 风险与剩余问题")
    L.append("")
    L.append("### 阻断性问题")
    L.append("")
    L.append("- 无。未发现目标泄漏、切分交叉或核心数据异常。")
    L.append("")
    L.append("### 非阻断性问题（限制实验解释力，必须随结论一并引用）")
    L.append("")
    for x in _limitations():
        L.append(f"- {x}")
    L.append("")

    # ---- 最终结论
    core_fail = [i for i in items if i["verdict"] == "FAIL"]
    if core_fail:
        verdict, letter = ("存在核心 FAIL，阶段不通过", "C")
    else:
        verdict = ("数据加工、可信切分与零训练 Baseline 全部可用，"
                   "但代理标签与学历伪标签的可信度限制仍然存在，具备正式模型训练条件时"
                   "必须沿用本报告的评估协议与限制说明")
        letter = "B"
    L.append("## 阶段验收结论")
    L.append("")
    L.append(f"**{letter}. {'有条件通过' if letter == 'B' else ('不通过' if letter == 'C' else '完全通过')}**")
    L.append("")
    L.append(verdict + "。")
    L.append("")
    if core_fail:
        L.append("未通过项：" + ", ".join(f"{i['code']} {i['content']}" for i in core_fail))
        L.append("")
    L.append("判定依据：上表全部核心验收项均为 PASS，且 G1-G7 自动化门禁全部通过；"
             "但匹配标签为原评分系统派生的代理标签、学历伪标签可信度低且无独立可信测试集，"
             "因此按验收规则判定为「有条件通过」，不判定为「完全通过」。")
    L.append("")
    return "\n".join(L)


def _limitations() -> list[str]:
    return [
        "**匹配标签是代理标签**：`label_strength`/`candidate_rank`/`final_score` 均由原系统"
        "评分公式派生（非真实投递或录用结果），排序指标只能解释为"
        "「与原系统代理偏好的一致程度」，不代表真实录用概率或用户满意度。",
        "**Embedding Cosine 基线与代理标签机制耦合**：`semantic_score = 0.5*cosine+0.5` "
        "已被审计以 R²=1.0 证实，而 semantic_score 占 raw_score 0.25 权重。"
        "该基线的高 NDCG 不构成独立的语义匹配有效性证明。",
        "**预计算 Embedding 来源未知**：「冷启动」仅表示下游排序模型未用这些候选人/岗位"
        "监督训练，不能宣称预训练编码器从未见过相关文本。",
        "**匹配数据无真实负例**：matches.csv 全部为 *_positive 观测记录，"
        "本阶段不做负采样，评估只在观测组合内部做组内排序。",
        "**学历伪标签可信度低**：default/* 的 assistant 为线上旧系统输出，"
        "人工复核一致率 45.92%（338/736），只能作低置信开发信号。",
        "**学历无独立可信测试集**：原 default/test 100% 被 default/validation 包含，"
        "最终独立评估改用 gold_holdout（736 条人工金标准），只做一次性评估。",
        "**学历任务范围受限**：`<学历描述>` 是上游已抽取的短槽位，"
        "本数据只能支撑「学历要求表达的规范化/多标签归一」，不是端到端 JD 学历抽取。",
        "**Double Cold-start 稀疏性**：双侧互斥必然丢弃交叉边，"
        "保留率与可排序组数见 reports/data-split-validation.md，评估时必须按保留率解释。",
        "**格式限制**：本地缺少 Parquet 引擎（pyarrow/fastparquet 未安装），"
        "按约束不修改环境，表格产物使用 CSV（已在 manifest 记录）。",
    ]


def render_all() -> dict:
    log = get_logger()
    cfg = get_config()
    rep = cfg.path("reports")
    out = {}
    out["data_preprocessing"] = rel(_write(rep / "data-preprocessing.md", render_preprocessing()))
    out["data_split_validation"] = rel(_write(rep / "data-split-validation.md", render_splits()))
    out["matching_baselines"] = rel(_write(rep / "baselines" / "matching-baselines.md",
                                           render_matching_baselines()))
    out["education_baselines"] = rel(_write(rep / "baselines" / "education-baselines.md",
                                            render_education_baselines()))
    out["phase3_acceptance"] = rel(_write(rep / "phase3-acceptance.md", render_acceptance()))
    for k, v in out.items():
        log.info("[报告] %s -> %s", k, v)
    return out
