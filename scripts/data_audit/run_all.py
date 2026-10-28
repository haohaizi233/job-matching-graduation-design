# -*- coding: utf-8 -*-
"""审计汇总：串起 data_audit 全部脚本，产出 reports/data-audit/audit-summary.json。

用法：
    python scripts/data_audit/run_all.py            # 只汇总（要求各子脚本已运行）
    python scripts/data_audit/run_all.py --run-all  # 先顺序执行全部子脚本再汇总

复用：
    scripts/hash_datasets.py 的 sha256_file —— 记录数据文件指纹（流式，不占内存），
    与 scripts/verify_data_integrity.py 保持同一套校验口径。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = C.ROOT

SUB_SCRIPTS = [
    "profile_datasets.py",
    "analyze_matching.py",
    "reverse_label_formula.py",
    "analyze_embeddings.py",
    "analyze_education.py",
    "analyze_risk.py",
]

SUB_OUTPUTS = {
    "dataset_profile": "dataset-profile.json",
    "matching_analysis": "matching-analysis.json",
    "label_formula": "label-formula.json",
    "embedding_analysis": "embedding-analysis.json",
    "education_analysis": "education-analysis.json",
    "risk_analysis": "risk-analysis.json",
}

DATA_FILES = {
    "cv.csv": C.CV,
    "job.csv": C.JOB,
    "matches.csv": C.MATCHES,
    "all_df.csv": C.RISK,
    "edu_train": C.EDU_TRAIN,
    "edu_validation": C.EDU_VAL,
    "edu_test": C.EDU_TEST,
    "edu_annotated": C.EDU_ANNOT,
}


def _load_sha256_helper():
    """复用 scripts/hash_datasets.py 的流式 sha256，避免重复实现。"""
    p = ROOT / "scripts" / "hash_datasets.py"
    spec = importlib.util.spec_from_file_location("hash_datasets", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.sha256_file


def run_sub_scripts() -> None:
    py = sys.executable
    for s in SUB_SCRIPTS:
        print("\n########## %s ##########" % s, file=sys.stderr)
        rc = subprocess.call([py, "-X", "utf8", str(HERE / s)])
        if rc != 0:
            print("子脚本 %s 退出码 %d" % (s, rc), file=sys.stderr)


def collect() -> dict:
    sha256_file = _load_sha256_helper()
    out = {
        "generated_by": "scripts/data_audit/run_all.py",
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "project_root": str(ROOT),
        "conda_env": "graduation-design",
        "scope": "第二阶段：数据集深度审计与建模可行性评估（只读，不训练模型）",
        "constraints_observed": [
            "未改写 data/raw 下任何文件",
            "未创建正式训练集 / 未训练模型 / 未下载预训练权重",
            "未安装或升级依赖",
            "未联网调用外部 AI API",
            "未修改 environment.yml 与既有环境验收报告",
            "未触碰 chinese-skillspan-benchmark/ 独立仓库",
        ],
        "data_files": {},
        "sub_reports": {},
        "key_findings": {},
    }

    # 数据文件指纹
    for name, p in DATA_FILES.items():
        if not p.is_file():
            out["data_files"][name] = {"error": "不存在"}
            continue
        meta = C.file_meta(p)
        meta["sha256_first_1mb"] = C.sha256_head(p, 1 << 20)
        print("  计算 %s 完整 SHA-256 ..." % name, file=sys.stderr)
        meta["sha256_full"] = sha256_file(str(p))
        out["data_files"][name] = meta

    # 子报告
    for key, fname in SUB_OUTPUTS.items():
        fp = C.OUT / fname
        if not fp.is_file():
            out["sub_reports"][key] = {"error": "未生成: %s" % C.rel(fp)}
            continue
        with open(fp, "r", encoding="utf-8") as f:
            obj = json.load(f)
        out["sub_reports"][key] = {
            "path": C.rel(fp),
            "bytes": fp.stat().st_size,
            "top_level_keys": list(obj.keys()),
        }
    return out


def add_key_findings(out: dict) -> None:
    """把最关键的结论以机器可读形式固定下来，供后续阶段直接引用。"""
    def _get(path, default=None):
        cur = out
        try:
            for k in path:
                cur = cur[k]
            return cur
        except Exception:
            return default

    # 从已生成的子 JSON 里读关键数值
    def load(name):
        fp = C.OUT / name
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)

    lf = load("label-formula.json")
    em = load("embedding-analysis.json")
    ed = load("education-analysis.json")
    rk = load("risk-analysis.json")
    mk = load("matching-analysis.json")

    out["key_findings"] = {
        "P1_supported_supervised_tasks": {
            "answer": [
                "岗位学历信息抽取（受限词表短答案生成 / 多标签分类）——数据量 19.7 万训练样本，可行",
                "简历—岗位匹配强度回归或排序（弱监督，标签由公式派生）——需自建负例与冷启动划分",
                "简历—岗位语义相似度（可用预计算 768 维向量与 semantic_score 作代理标签）",
                "岗位推荐与排序（Learning-to-Rank，可用 candidate_rank 作组内序）",
                "简历技能缺口分析（基于 clean_skills 集合差，无监督/规则）",
            ],
            "not_supported_without_new_labeling": [
                "真实匹配结果二分类（数据中无真实投递/录用结果）",
                "招聘诈骗识别的监督学习（scam_probability 非人工真值）",
                "序列标注 / NER（学历数据无 token 级标注）",
            ],
        },
        "P2_six_score_label_leakage": {
            "answer": "存在完全确定的目标泄漏",
            "chain": [
                "semantic_score = 0.5 * cosine(cv_embedding, job_embedding) + 0.5   (R²=1.0, pearson=1.0)",
                "raw_score = 0.25*semantic + 0.35*skill + 0.20*position + 0.10*category"
                " + 0.05*experience + 0.05*education   (max|err|=%s)" % lf["raw_score_formula"]["max_abs_error"],
                "final_score = 0.7 * raw_score + 0.3 * candidate_rank_pct   (max|err|=8.88e-16, R²=1.0)",
                "label_strength = weak(<0.58) / medium(0.58~0.68) / strong(>=0.68)   (复现率 1.0, 0 例外)",
                "candidate_rank = 组内 final_score 降序名次   (9532/9532 组复现)",
            ],
            "verdict": (
                "六维评分 + raw_score / final_score / candidate_rank / candidate_rank_pct "
                "共同构成一条闭环派生链，直接预测 label_strength 等价于复现生成公式，属目标泄漏。"),
            "leakage_feature_list": lf["leakage_verdict"]["leakage_feature_list"],
        },
        "P3_enough_data_for_evaluable_match_model": {
            "answer": "有条件足够，但当前标签不能支撑'真实匹配'结论",
            "facts": {
                "matches_rows": mk["relations"]["matches_rows"],
                "candidates": mk["relations"]["matches_unique_candidate_id"],
                "jobs": mk["relations"]["matches_unique_job_id"],
                "observed_pair_ratio_pct": mk["relations"]["observed_pair_ratio_pct"],
                "label_dist": mk["labels"]["label_strength_value_counts"],
                "strong_positive_ratio_pct": mk["labels"]["strong_positive_ratio_pct"],
                "pair_duplicated": mk["relations"]["pair_duplicated"],
                "pair_label_conflict": mk["relations"]["pair_label_conflict"],
            },
            "verdict": (
                "样本量（12.3 万 pair / 9532 人 / 1164 岗）足够训练与评估一个可复现的匹配/排序模型；"
                "但标签为公式派生、无真实负例、strong_positive 仅 774 条（0.63%），"
                "只能支撑'复现该评分体系'或'基于语义/技能的排序'这类目标，"
                "不能支撑'预测真实匹配结果'。"),
        },
        "P4_must_fix_before_training": [
            "matches.csv 无真实负例：weak_positive 是正例的一档，未观测组合也不等于负例，必须设计负采样方案。",
            "strong_positive 仅 %s 条（%s%%），medium/strong 比 %s:1，必须做分层采样或改用回归/排序目标。"
            % (mk["labels"]["strong_positive_count"], mk["labels"]["strong_positive_ratio_pct"],
               mk["labels"]["imbalance_ratio_medium_to_strong"]),
            "标签链闭合：任何使用六维评分/分数/排名字段的特征集都构成目标泄漏，必须从特征中剔除。",
            "job-education 的 default/train|validation|test 的 assistant 是线上旧系统输出（伪标签），"
            "与 736 条人工金标准只有 %s%% 一致，必须先决定是用伪标签做弱监督还是只用人工 736 条。"
            % ed["label_provenance"]["level_fact_human_labeled_subset"][
                "人工正确结果_equals_validation_assistant_pct"],
            "job-education 的 test 完全被 validation 包含（job_id 与 user 文本均 100%% 重合），"
            "必须重新划分，否则在 validation 选模型后报 test 指标等价于测试集调参。",
            "all_df.csv 有 %s 行整行重复（%s%%），去重后才可建模。"
            % (rk["table"]["whole_row_duplicates"], rk["table"]["whole_row_duplicates_pct"]),
            "matches.csv 仅覆盖全组合的 %s%%，且同一候选人/岗位跨行高度重叠，行级随机划分必然泄漏。"
            % mk["relations"]["observed_pair_ratio_pct"],
        ],
        "P5_next_stage_plan": {
            "split_strategy": [
                "主评估采用 candidate_id 分组切分（GroupShuffleSplit / GroupKFold），杜绝同人跨集合。",
                "增加 job_id 冷启动切分（按 job_id 分组）评估对未见岗位的泛化。",
                "增加 candidate_id × job_id 双冷启动（两组都互斥）作为最严指标。",
                "job-education 重新切分：从 validation 中剥离 test 的 22730 个 job_id，"
                "或把 default 三份合并后按 job_id 重新做 8:1:1 分层切分。",
                "所有切分固定随机种子并落盘到 data/splits/，切分清单写入 JSON 以便复现。",
            ],
            "preprocessing": [
                "embedding 字段解析为 float32 矩阵并落盘 .npy，不再重复解析字符串向量。",
                "clean_skills 字符串化列表还原为 list[str] 并做大小写/同义词归一。",
                "学历标签统一为 6 个 token 的有序多标签（博士/硕士/本科/大专/学历不限/学历不明）。",
                "all_df.csv 整行去重并保留去重映射。",
            ],
            "negative_sampling": [
                "候选方案 A：按候选人做组内负采样——从该候选人未观测的岗位中随机抽 k 个作负例。",
                "候选方案 B：按 final_score 分位做难负例挖掘——取 low-score 观测对作难负例。",
                "候选方案 C：BPR 成对排序——只用组内序（candidate_rank）构造偏好对，不显式建负类。",
                "本阶段不生成正式负例，上述方案留待第三阶段验证。",
            ],
        },
        "open_questions": [
            "六维评分（semantic/skill/position/category/experience/education）中除 semantic_score 外，"
            "其余 5 个的计算方法未知，数据未提供。",
            "candidate_rank_pct 的确切定义未知（其分母在候选人/岗位两个方向上都不一致，"
            "无法从数据自证），只知道它是 final_score 的线性输入之一。",
            "0.58 / 0.68 两个标签阈值的设定依据未知。",
            "embedding 的编码模型未知（README 明确声明未指定），不能仅凭 768 维推断。",
            "学历数据的 default 标签虽为线上系统输出，但该系统本身的准确率未知（人工 736 条显示约 %s%%）。"
            % ed["label_provenance"]["level_fact_human_labeled_subset"][
                "人工正确结果_equals_validation_assistant_pct"],
            "scam_probability 的生成模型与校准含义未知。",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-all", action="store_true", help="先顺序执行全部子脚本")
    args = ap.parse_args()

    C.ensure_out()
    if args.run_all:
        run_sub_scripts()

    out = collect()
    add_key_findings(out)
    C.jdump(out, C.OUT / "audit-summary.json")

    print("\n=== 审计汇总已写出 ===")
    print("报告目录:", C.rel(C.OUT))
    for k, v in out["sub_reports"].items():
        print("  %-20s %s" % (k, v.get("path", v.get("error"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
