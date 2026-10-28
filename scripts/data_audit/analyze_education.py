# -*- coding: utf-8 -*-
"""岗位学历解析数据专项分析：标签结构、类别分布、文本形态、跨集合重复。

产出：reports/data-audit/education-analysis.json
用法：python scripts/data_audit/analyze_education.py

只读 data/raw；大文件分块读取；不输出岗位描述原文，只输出标签与统计量。
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

OUT_JSON = "education-analysis.json"

FILES = {
    "train": C.EDU_TRAIN,
    "validation": C.EDU_VAL,
    "test": C.EDU_TEST,
    "annotated": C.EDU_ANNOT,
}

TAG_EDU = re.compile(r"<学历描述>(.*?)</学历描述>", re.S)
TAG_NAME = re.compile(r"<岗位名称>(.*?)</岗位名称>", re.S)
TAG_DESC = re.compile(r"<岗位描述>(.*?)</岗位描述>", re.S)

# 常见学历词（用于统计表达变体，不用于生成训练标签）
EDU_WORDS = ["博士", "硕士", "研究生", "本科", "学士", "大专", "专科", "高职",
             "中专", "高中", "不限", "学历"]


def label_tokens(s) -> list:
    """把 '博士、硕士、本科' 拆成有序 token 列表。"""
    t = str(s).strip()
    if not t or t.lower() == "nan":
        return []
    parts = re.split(r"[、,，/|\s]+", t)
    return [p.strip() for p in parts if p.strip()]


def analyze_file(name: str, path: Path) -> dict:
    print("  处理 %s ..." % name, file=sys.stderr)
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    r = {
        "file": C.file_meta(path),
        "rows": int(len(df)),
        "columns": list(df.columns),
    }

    # --- 输入文本形态
    if "user" in df.columns:
        u = df["user"].astype(str)
        r["user_text_len"] = C.text_len_summary(u)
        has_name = u.str.contains(TAG_NAME).sum()
        has_desc = u.str.contains(TAG_DESC).sum()
        has_edu = u.str.contains(TAG_EDU).sum()
        r["user_tag_coverage"] = {
            "has_岗位名称": int(has_name),
            "has_岗位描述": int(has_desc),
            "has_学历描述": int(has_edu),
            "has_学历描述_pct": round(100.0 * has_edu / max(1, len(u)), 3),
        }
        # <学历描述> 里的原始表达（这是模型可直接利用的抽取线索）
        edu_txt = u.str.extract(TAG_EDU, expand=False)
        r["学历描述_field"] = {
            "missing": int(edu_txt.isna().sum()),
            "text_len": C.text_len_summary(edu_txt.dropna()),
            "unique_values": int(edu_txt.nunique(dropna=True)),
            "top_values": C.value_counts(edu_txt, 25),
            "contains_multiple_degree_words_pct": round(
                100.0 * edu_txt.dropna().astype(str).apply(
                    lambda s: sum(w in s for w in ["博士", "硕士", "本科", "大专", "专科"]) > 1
                ).mean(), 3) if edu_txt.notna().any() else None,
        }
        # 规则难点：非标准表达
        hard_patterns = {
            "含_及以上": r"及以上",
            "含_或以上": r"或以上",
            "含_学历不限": r"学历不限|不限学历|学历：?\s*不限",
            "含_全日制": r"全日制",
            "含_统招": r"统招",
            "含_学士学位": r"学士学位",
            "含_硕士学位": r"硕士学位",
            "含_博士学位": r"博士学位",
            "含_研究生学历": r"研究生学历|研究生毕业",
            "含_大专/专科混用": r"大专|专科",
            "含_本科及以上_但未提其他层级": r"本科及以上",
            "含_中专/中技/高中": r"中专|中技|高中|职高",
            "含_应届/在校": r"应届|在校生|在校学生",
            "含_英文学位词": r"Bachelor|Master|PhD|Ph\.?D|bachelor|master",
            "含_数字层级如_985_211": r"985|211|双一流",
        }
        hard = {}
        for k, pat in hard_patterns.items():
            hard[k] = int(u.str.contains(pat, regex=True).sum())
        r["hard_chinese_expressions_in_user"] = hard

    # --- 标签结构
    lab_col = "人工正确结果" if (name == "annotated" and "人工正确结果" in df.columns) else "assistant"
    if lab_col in df.columns:
        lab = df[lab_col]
        r["label_column_used"] = lab_col
        r["label_missing"] = int(lab.isna().sum())
        r["label_missing_pct"] = round(100.0 * lab.isna().mean(), 3)
        present = lab.dropna().astype(str)
        r["label_present_rows"] = int(len(present))
        r["label_unique_values"] = int(present.nunique())
        r["label_value_counts"] = C.value_counts(present, 40)
        toks = present.map(label_tokens)
        n_tok = toks.map(len)
        r["label_token_count_dist"] = {str(k): int(v) for k, v in
                                       n_tok.value_counts().sort_index().items()}
        r["multi_label_rows"] = int((n_tok > 1).sum())
        r["multi_label_pct"] = round(100.0 * (n_tok > 1).mean(), 3) if len(n_tok) else 0.0
        r["empty_label_rows"] = int((n_tok == 0).sum())
        flat = Counter()
        for t in toks:
            for x in t:
                flat[x] += 1
        r["label_token_vocabulary"] = dict(flat.most_common(40))
        r["label_token_vocab_size"] = int(len(flat))
        # 是否存在"无学历要求"类标签
        no_req = [k for k in flat if any(w in k for w in ["不限", "无", "未提", "其他"])]
        r["no_education_requirement_tokens"] = no_req
        r["no_education_requirement_rows"] = int(sum(flat[k] for k in no_req))
        # 标签是否为封闭小集合
        r["label_is_closed_small_set"] = bool(present.nunique() <= 60)

    # --- 其他列
    for c in ["ai", "diff", "user_short2", "id", "job_id"]:
        if c in df.columns:
            r["col_%s" % c] = {
                "dtype": str(df[c].dtype),
                "missing": int(df[c].isna().sum()),
                "unique": int(df[c].nunique(dropna=True)),
            }
    if "ai" in df.columns and "assistant" in df.columns:
        both = df["ai"].notna() & df["assistant"].notna()
        r["ai_vs_assistant_agreement_pct"] = round(
            100.0 * (df.loc[both, "ai"].astype(str) ==
                     df.loc[both, "assistant"].astype(str)).mean(), 4) if both.any() else None
        r["ai_vs_assistant_compared_rows"] = int(both.sum())
    return r


def cross_split_overlap() -> dict:
    """训练/验证/测试/标注集之间按 user 文本与 job_id 的重叠。"""
    print("  计算跨集合文本重复 ...", file=sys.stderr)
    frames = {}
    for name, path in FILES.items():
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False,
                         usecols=[c for c in ["user", "job_id", "assistant"] if c in
                                  pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns])
        frames[name] = df

    out = {}
    keys = list(frames)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            sa = set(frames[a]["user"].dropna().astype(str))
            sb = set(frames[b]["user"].dropna().astype(str))
            inter = sa & sb
            ja = set(frames[a]["job_id"].dropna().astype(str)) if "job_id" in frames[a] else set()
            jb = set(frames[b]["job_id"].dropna().astype(str)) if "job_id" in frames[b] else set()
            out["%s__vs__%s" % (a, b)] = {
                "user_text_unique_a": int(len(sa)),
                "user_text_unique_b": int(len(sb)),
                "user_text_overlap": int(len(inter)),
                "user_text_overlap_pct_of_b": round(100.0 * len(inter) / max(1, len(sb)), 3),
                "job_id_overlap": int(len(ja & jb)),
                "job_id_unique_a": int(len(ja)),
                "job_id_unique_b": int(len(jb)),
            }
    # 集合内重复
    for name, df in frames.items():
        u = df["user"].dropna().astype(str)
        out["internal_dup__%s" % name] = {
            "rows": int(len(u)),
            "unique_user_text": int(u.nunique()),
            "duplicate_user_text_rows": int(u.duplicated().sum()),
            "duplicate_user_text_pct": round(100.0 * u.duplicated().mean(), 3),
        }
    return out


def annotated_agreement() -> dict:
    """人工标注评测集中 新旧模型 / 人工金标准 之间的一致性。

    注意：字符串比较与 token 集合比较分开给出，
    因为模型输出存在 '博士、硕士' vs '硕士、博士' 这类顺序差异。
    """
    print("  计算人工标注一致性 ...", file=sys.stderr)
    df = pd.read_csv(C.EDU_ANNOT, encoding="utf-8-sig", low_memory=False)
    r = {"rows": int(len(df))}
    cols = {c: int(df[c].notna().sum()) for c in df.columns}
    r["non_null_per_column"] = cols
    n = df["人工正确结果"].notna()
    r["human_labeled_rows"] = int(n.sum())
    sub = df[n].copy()
    if len(sub):
        gold = sub["人工正确结果"].astype(str)
        old = sub["线上学历-旧的"].astype(str)
        new = sub["模型结果-新的"].astype(str)
        asst = sub["assistant"].astype(str)

        def tok(s):
            t = str(s).strip()
            if not t or t.lower() == "nan":
                return frozenset()
            return frozenset(p.strip() for p in re.split(r"[、,，/|\s]+", t) if p.strip())

        r["string_equality_pct"] = {
            "assistant_equals_人工正确结果": round(100.0 * (asst == gold).mean(), 4),
            "线上学历旧_equals_人工正确结果": round(100.0 * (old == gold).mean(), 4),
            "模型结果新_equals_人工正确结果": round(100.0 * (new == gold).mean(), 4),
            "线上学历旧_equals_模型结果新": round(100.0 * (old == new).mean(), 4),
        }
        tg, to, tn = gold.map(tok), old.map(tok), new.map(tok)
        r["token_set_equality_pct"] = {
            "线上学历旧_equals_人工正确结果": round(100.0 * (to == tg).mean(), 4),
            "模型结果新_equals_人工正确结果": round(100.0 * (tn == tg).mean(), 4),
            "线上学历旧_equals_模型结果新": round(100.0 * (to == tn).mean(), 4),
        }
        r["token_set_confusion"] = {
            "old_correct_and_new_correct": int(((to == tg) & (tn == tg)).sum()),
            "old_correct_and_new_wrong": int(((to == tg) & (tn != tg)).sum()),
            "old_wrong_and_new_correct": int(((to != tg) & (tn == tg)).sum()),
            "old_wrong_and_new_wrong": int(((to != tg) & (tn != tg)).sum()),
        }
        r["token_set_confusion_note"] = (
            "old 与 new 在这 736 行上字符串/集合均无一相同，因此 'old 对且 new 对' 必为 0，"
            "这是数据组织造成的机械结果，不能解读为两个系统在统计上互斥。")
        r["new_error_direction"] = {
            "new_tokens_more_than_gold": int((tn.map(len) > tg.map(len)).sum()),
            "new_tokens_fewer_than_gold": int((tn.map(len) < tg.map(len)).sum()),
        }
        for c in ["【线上学历-旧的】是否正确", "【模型结果-新的】是否正确"]:
            r["flag_%s" % c] = C.value_counts(sub[c], 10)
        r["是否英文岗位"] = C.value_counts(df["是否英文岗位"], 10)
        r["人工正确结果_value_counts"] = C.value_counts(sub["人工正确结果"], 30)

        # 抽取失败的脏输出
        dirty = new.str.contains(r"岗位描述|学历描述|岗位名称|？|、学历、|工作经验如何", regex=True)
        r["模型结果新_dirty_output_rows"] = int(dirty.sum())
        r["模型结果新_unique_values"] = int(new.nunique())
        r["线上学历旧_unique_values"] = int(old.nunique())
    return r


def label_provenance() -> dict:
    """追查 job-education/default 三个切分的 assistant 标签来源。"""
    print("  追查标签来源（validation / annotated 对齐）...", file=sys.stderr)
    v = pd.read_csv(C.EDU_VAL, encoding="utf-8-sig", low_memory=False,
                    usecols=["job_id", "user", "assistant"])
    a = pd.read_csv(C.EDU_ANNOT, encoding="utf-8-sig", low_memory=False)
    m = a.merge(v, on="job_id", how="left", suffixes=("_annot", "_val"))
    n = m["人工正确结果"].notna()
    sub = m[n]
    full = {
        "validation_rows": int(len(v)),
        "annotated_rows": int(len(a)),
        "annotated_job_id_all_in_validation": bool(set(a["job_id"]).issubset(set(v["job_id"]))),
        "user_text_identical_pct": round(
            100.0 * (m["user_annot"].astype(str) == m["user_val"].astype(str)).mean(), 4),
        "线上学历旧_equals_validation_assistant_pct": round(
            100.0 * (m["线上学历-旧的"].astype(str) == m["assistant_val"].astype(str)).mean(), 4),
        "模型结果新_equals_validation_assistant_pct": round(
            100.0 * (m["模型结果-新的"].astype(str) == m["assistant_val"].astype(str)).mean(), 4),
    }
    gold_only = {
        "rows": int(len(sub)),
        "人工正确结果_equals_validation_assistant_pct": round(
            100.0 * (sub["人工正确结果"].astype(str) == sub["assistant_val"].astype(str)).mean(), 4),
        "annotated_assistant_equals_validation_assistant_pct": round(
            100.0 * (sub["assistant_annot"].astype(str) == sub["assistant_val"].astype(str)).mean(), 4),
    }
    pct_agree = gold_only["人工正确结果_equals_validation_assistant_pct"]
    return {
        "level_fact": full,
        "level_fact_human_labeled_subset": gold_only,
        "conclusion": (
            "validation 切分的 assistant 标签与 annotated 中的 '线上学历-旧的' 列 100% 一致，"
            "说明 default 三个切分的 assistant 是上游线上旧系统的输出（伪标签 / 远监督），"
            "不是人工标注。人工复核的 736 行中，人工金标准与该伪标签只有 "
            + f"{pct_agree:.2f}" + "% 一致，即约 " + f"{100.0 - pct_agree:.2f}"
            + "% 的既有标签与人工结论不符。"),
        "must_not_claim": [
            "不得把 default/train|validation|test 的 assistant 称为人工标注真值。",
            "不得直接把这三份数据的标签当作'正确答案'训练后再用同源标签评估。",
        ],
    }


def split_containment() -> dict:
    """检查 train/val/test 之间是否互斥，是否存在子集包含关系。"""
    print("  检查切分包含关系 ...", file=sys.stderr)
    cols = ["job_id", "user"]
    tr = pd.read_csv(C.EDU_TRAIN, encoding="utf-8-sig", low_memory=False, usecols=cols)
    va = pd.read_csv(C.EDU_VAL, encoding="utf-8-sig", low_memory=False, usecols=cols)
    te = pd.read_csv(C.EDU_TEST, encoding="utf-8-sig", low_memory=False, usecols=cols)
    out = {
        "rows": {"train": int(len(tr)), "validation": int(len(va)), "test": int(len(te))},
        "job_id_unique": {"train": int(tr["job_id"].nunique()),
                          "validation": int(va["job_id"].nunique()),
                          "test": int(te["job_id"].nunique())},
    }
    sets = {"train": set(tr["job_id"]), "validation": set(va["job_id"]), "test": set(te["job_id"])}
    for a, b in [("train", "validation"), ("train", "test"), ("validation", "test")]:
        inter = sets[a] & sets[b]
        out["job_id_overlap__%s__vs__%s" % (a, b)] = {
            "overlap": int(len(inter)),
            "pct_of_%s" % b: round(100.0 * len(inter) / max(1, len(sets[b])), 3),
            "is_subset_%s_in_%s" % (b, a): bool(sets[b] <= sets[a]),
        }
    utr, uva, ute = set(tr["user"].astype(str)), set(va["user"].astype(str)), set(te["user"].astype(str))
    for a, b, sa, sb in [("train", "validation", utr, uva),
                         ("train", "test", utr, ute),
                         ("validation", "test", uva, ute)]:
        out["user_text_overlap__%s__vs__%s" % (a, b)] = {
            "overlap": int(len(sa & sb)),
            "pct_of_%s" % b: round(100.0 * len(sa & sb) / max(1, len(sb)), 3),
            "is_subset_%s_in_%s" % (b, a): bool(sb <= sa),
        }
    out["risk"] = (
        "若 test 的 job_id / user 文本被 validation 完全包含，则在 validation 上做模型选择"
        "后再报 test 指标等价于在测试集上调参，构成数据泄漏。")
    return out


def task_type_assessment() -> dict:
    return {
        "label_structure_observed": (
            "标签是 '学历' 的短字符串，常见形态为单值（如 '本科'）或多值枚举（如 "
            "'博士、硕士、本科'），不是 token 级 BIO/BIOS 序列标注，也不是 span 偏移。"),
        "input_structure_observed": (
            "输入是 <岗位名称>/<岗位描述>/<学历描述> 三段 XML-like 拼接的长文本，"
            "其中 <学历描述> 已经是上游抽取结果，构成强先验线索。"),
        "conclusion": {
            "most_natural": "信息抽取（生成式短答案抽取），输出为受限学历词表上的短序列",
            "also_viable": [
                "多标签分类（把 '博士、硕士、本科' 拆成 4~6 个学历层级的多标签）",
                "有序多分类（映射为最低学历要求的一个层级）",
                "规则 + 模型混合解析（<学历描述> 走规则，描述正文走模型兜底）",
            ],
            "not_supported_by_data": [
                "序列标注 / NER：数据中不存在 token 级标注、span 起止偏移或 BIO 标签，"
                "不能直接做 NER 训练。",
            ],
        },
    }


def main() -> int:
    C.ensure_out()
    out = {
        "generated_by": "scripts/data_audit/analyze_education.py",
        "note": "只读审计；未修改任何原始文件。不输出岗位描述原文。",
        "files": {name: analyze_file(name, p) for name, p in FILES.items()},
        "cross_split": cross_split_overlap(),
        "annotated_agreement": annotated_agreement(),
        "label_provenance": label_provenance(),
        "split_containment": split_containment(),
        "task_type_assessment": task_type_assessment(),
    }
    C.jdump(out, C.OUT / OUT_JSON)

    print("=== 各文件规模 ===")
    print(pd.Series({k: v["rows"] for k, v in out["files"].items()}).to_string())
    print("\n=== 标签列使用与分布（前 15）===")
    for k, v in out["files"].items():
        print("--", k, "label col =", v.get("label_column_used"),
              "missing =", v.get("label_missing"))
        print(pd.Series(v.get("label_value_counts", {})).head(15).to_string())
        print("   multi_label_pct =", v.get("multi_label_pct"),
              " vocab_size =", v.get("label_token_vocab_size"))
    print("\n=== 人工标注一致性 ===")
    print(pd.Series(out["annotated_agreement"]).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
