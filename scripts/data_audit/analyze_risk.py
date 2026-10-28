# -*- coding: utf-8 -*-
"""中文招聘风险数据专项分析：字段质量、scam_probability 来源判断。

产出：reports/data-audit/risk-analysis.json
用法：python scripts/data_audit/analyze_risk.py

只读 data/raw；不输出公司名/地址原文，只输出统计量。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

OUT_JSON = "risk-analysis.json"


def analyze(df: pd.DataFrame) -> dict:
    r = {
        "rows": int(len(df)),
        "columns": list(df.columns),
        "whole_row_duplicates": int(df.duplicated().sum()),
        "whole_row_duplicates_pct": round(100.0 * df.duplicated().mean(), 4),
        "columns_profile": {},
    }
    for c in df.columns:
        s = df[c]
        item = {
            "dtype": str(s.dtype),
            "missing": int(s.isna().sum()),
            "missing_pct": round(100.0 * s.isna().mean(), 4),
            "unique": int(s.nunique(dropna=True)),
        }
        if c in ("job_name", "company_name", "company_address"):
            item["text_len"] = C.text_len_summary(s)
            item["empty_or_tiny_len_le3"] = int((s.astype(str).str.len() <= 3).sum())
        elif pd.api.types.is_numeric_dtype(s):
            item["numeric"] = C.num_summary(s)
        else:
            item["value_counts_top"] = C.value_counts(s, 25)
        r["columns_profile"][c] = item
    return r


def scam_field(df: pd.DataFrame) -> dict:
    s = pd.to_numeric(df["scam_probability"], errors="coerce")
    r = {
        "dtype_in_csv": str(df["scam_probability"].dtype),
        "missing": int(s.isna().sum()),
        "numeric_summary": C.num_summary(s),
        "unique_values_sorted": sorted(int(v) for v in s.dropna().unique()),
        "unique_value_count": int(s.nunique(dropna=True)),
        "value_counts": C.value_counts(s, 40),
        "is_integer_valued": bool(np.all(np.isclose(s.dropna() % 1, 0))),
        "all_multiples_of_10": bool(np.all(np.isclose((s.dropna() % 10), 0))),
        "multiples_of_10_pct": round(100.0 * float(np.mean(np.isclose(s.dropna() % 10, 0))), 4),
        "in_0_100_range": bool(s.dropna().between(0, 100).all()),
    }
    # 与其它字段的关联（判断它是真值还是规则分数）
    assoc = {}
    if "job_salary" in df.columns:
        sal = pd.to_numeric(df["job_salary"], errors="coerce")
        assoc["pearson_with_job_salary"] = round(float(sal.corr(s)), 6)
    for c in ["work_experience", "educational_requirements", "job_type"]:
        if c in df.columns:
            grp = df.groupby(df[c].astype(str)).apply(lambda g: float(g["scam_probability"].mean()),
                                                      include_groups=False)
            assoc["mean_scam_by_%s" % c] = {str(k): round(v, 4) for k, v in
                                            grp.sort_values(ascending=False).head(15).items()}
    r["associations"] = assoc

    # 结论
    r["assessment"] = {
        "level_fact": [
            "字段名为 scam_probability，取值域为整数百分数 0~100。",
            "取值集合有限（见 unique_values_sorted），且绝大多数为 10 的整数倍。",
            "数据中不存在任何'是否为诈骗'的布尔真值列、人工复核结论列或标注来源列。",
        ],
        "level_inference": [
            "取值离散、且集中在 10 的倍数，强烈提示它是由某个风险评分模型/规则输出后"
            "再做粗粒度映射得到的分数，而不是人工核实的诈骗真值概率。",
        ],
        "level_unknown": [
            "无法从数据本身确定生成该分数的模型、规则或人工流程。",
            "无法确定分数的校准含义（例如 40 是否真的代表 40% 诈骗概率）。",
        ],
        "usable_as_supervised_label": False,
        "reason": (
            "缺少人工核实的真值列，把它当作监督标签会把上游模型的偏差直接传递到下游，"
            "等价于学习一个未知模型的输出，不能作为'诈骗识别'的可信监督信号。"),
        "usable_as": [
            "可作为弱监督 / 远程监督（distant supervision）信号，用于构建可演示的风险打分模块，"
            "但必须在报告中明确标注为'上游风险分数'而非'人工标注真值'。",
            "可用于无监督异常检测的对照组。",
        ],
    }
    return r


def main() -> int:
    C.ensure_out()
    print("读取 all_df.csv ...", file=sys.stderr)
    df = pd.read_csv(C.RISK, encoding="utf-8-sig", low_memory=False)
    out = {
        "generated_by": "scripts/data_audit/analyze_risk.py",
        "file": C.file_meta(C.RISK),
        "note": "只读审计；未修改任何原始文件。不输出公司名/地址原文。",
        "table": analyze(df),
        "scam_probability": scam_field(df),
        "merge_recommendation": {
            "merge_with_matching_dataset_now": False,
            "reason": (
                "两个数据集的键完全不同：all_df.csv 没有 candidate_id / job_id，"
                "只有 job_name / company_name 文本；主匹配数据集的 job_id 为整数自增键。"
                "没有可靠连接键，强行按岗位名文本连接会产生大量错配。"),
            "when_to_merge": "仅在后续明确要做中文岗位风险模块、且能建立可靠连接键或独立建模时再考虑。",
        },
    }
    C.jdump(out, C.OUT / OUT_JSON)

    print("=== 表结构 ===")
    print(pd.Series({k: v for k, v in out["table"].items() if not isinstance(v, dict)}).to_string())
    print(pd.DataFrame({c: {k: v for k, v in p.items() if isinstance(v, (int, float, str))}
                        for c, p in out["table"]["columns_profile"].items()}).T.to_string())
    print("\n=== scam_probability ===")
    sp = out["scam_probability"]
    print("unique_value_count =", sp["unique_value_count"],
          " is_integer =", sp["is_integer_valued"],
          " all_multiples_of_10 =", sp["all_multiples_of_10"])
    print(pd.Series(sp["value_counts"]).to_string())
    print("\n=== 关联 ===")
    print(pd.Series({k: v for k, v in sp["associations"].items()
                     if isinstance(v, (int, float))}).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
