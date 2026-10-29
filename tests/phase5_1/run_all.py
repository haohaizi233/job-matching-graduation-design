# -*- coding: utf-8 -*-
"""Phase5-1 业务推理服务测试运行器（stdlib unittest，不引入 pytest）。

用法:
    python tests/phase5_1/run_all.py           # 全部测试
    python tests/phase5_1/run_all.py S13       # 只跑 S13 场景

输出:
    控制台逐项 PASS/FAIL + reports/phase5-1/test-results.json
    （附 test-results.md 摘要）
退出码: 0 = 全部通过，1 = 存在 FAIL/ERROR

纪律：
  * 只用合成夹具，不读 data/raw 全量语料、不跑任何 GPU 训练；
  * 不触碰 models/ 与 data/independent_eval/（S24 有前后指纹校验）；
  * 严禁跳过失败测试或降低既有门禁标准。
"""
from __future__ import annotations

import json
import re
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TEST_MODULES = [
    ("S01", "test_s01_s04_documents", "中文 TXT 简历解析"),
    ("S02", "test_s01_s04_documents", "中文 DOCX 简历解析"),
    ("S03", "test_s01_s04_documents", "可提取文本 PDF 解析"),
    ("S04", "test_s01_s04_documents", "扫描版 PDF / 空文本拒识"),
    ("S05", "test_s05_s07_profile", "技能归一化与来源标注"),
    ("S06", "test_s05_s07_profile", "简历字段证据溯源"),
    ("S07", "test_s05_s07_profile", "岗位必要技能与加分技能区分"),
    ("S08", "test_s08_s09_education_validation", "学历规则回退与异常拒识"),
    ("S09", "test_s08_s09_education_validation", "缺字段与非法数据验证"),
    ("S10", "test_s10_s12_ranking", "Baseline 稳定排序"),
    ("S11", "test_s10_s12_ranking", "重复岗位处理"),
    ("S12", "test_s10_s12_ranking", "同分稳定排序"),
    ("S13", "test_s13_s16_model", "MatchPredictor 合法输入适配"),
    ("S14", "test_s13_s16_model", "禁止模型目标值泄漏"),
    ("S15", "test_s13_s16_model", "模型权重缺失降级"),
    ("S16", "test_s13_s16_model", "中文不兼容模型拒绝正式模式"),
    ("S17", "test_s17_s18_results", "score_type 明确且正确"),
    ("S18", "test_s17_s18_results", "匹配解释与实际证据一致"),
    ("S19", "test_s19_s22_api", "PII 日志脱敏"),
    ("S20", "test_s19_s22_api", "API 正常/异常/边界"),
    ("S21", "test_s19_s22_api", "模型加载仅在初始化或缓存失效时"),
    ("S22", "test_s19_s22_api", "同输入同模型版本确定性"),
    ("S23", "test_s23_s24_demo_guard", "离线闭环演示运行成功"),
    ("S24", "test_s23_s24_demo_guard", "不触碰历史模型与 Gold 盲测数据"),
]


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []

    def _group_of(self, test) -> str:
        m = re.match(r"^S(\d+)", type(test).__name__)
        return f"S{int(m.group(1)):02d}" if m else "S?"

    def _add(self, test, status: str, detail: str):
        self.records.append({"group": self._group_of(test), "test": str(test),
                             "status": status, "detail": detail})

    def addSuccess(self, test):
        super().addSuccess(test)
        self._add(test, "PASS", "")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, "FAIL", self._exc_info_to_string(err, test)[-1500:])

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, "ERROR", self._exc_info_to_string(err, test)[-1500:])

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._add(test, "SKIP", reason)


def _filter_suite(suite: unittest.TestSuite, tag: str) -> unittest.TestSuite:
    out = unittest.TestSuite()
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            out.addTests(_filter_suite(test, tag))
        elif type(test).__name__.upper().startswith(tag):
            out.addTest(test)
    return out


def main() -> int:
    only = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    seen_modules: set[str] = set()
    for tag, mod, _title in TEST_MODULES:
        if only and tag != only:
            continue
        if mod in seen_modules:
            continue
        seen_modules.add(mod)
        loaded = loader.loadTestsFromName(mod)
        suite.addTests(_filter_suite(loaded, tag) if only else loaded)

    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    t0 = time.time()
    result = runner.run(suite)
    seconds = round(time.time() - t0, 2)

    records = result.records
    summary: dict[str, dict] = {}
    for tag, mod, title in TEST_MODULES:
        rows = [r for r in records if r["group"] == tag]
        if not rows:
            continue
        summary[tag] = {
            "title": title,
            "module": mod,
            "total": len(rows),
            "pass": sum(1 for r in rows if r["status"] == "PASS"),
            "fail": sum(1 for r in rows if r["status"] in ("FAIL", "ERROR")),
            "skip": sum(1 for r in rows if r["status"] == "SKIP"),
        }
    ok = not (result.failures or result.errors)
    out = {
        "generated_by": "tests/phase5_1/run_all.py",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": seconds,
        "ok": ok,
        "totals": {"tests": len(records),
                   "pass": sum(1 for r in records if r["status"] == "PASS"),
                   "fail": sum(1 for r in records if r["status"] in ("FAIL", "ERROR")),
                   "skip": sum(1 for r in records if r["status"] == "SKIP")},
        "groups": summary,
        "records": records,
    }
    out_dir = ROOT / "reports" / "phase5-1"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "test-results.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    lines = [
        "# Phase5-1 业务推理服务自动化测试报告", "",
        f"- 生成时间：{out['created_at']} ｜ 耗时：{seconds}s",
        f"- 总计 {out['totals']['tests']} 项：PASS={out['totals']['pass']} "
        f"FAIL={out['totals']['fail']} SKIP={out['totals']['skip']} ｜ ok={ok}", "",
        "| 组 | 场景 | 总数 | 通过 | 失败 | 跳过 |",
        "|---|---|---|---|---|---|",
    ]
    for tag, mod, title in TEST_MODULES:
        if tag in summary:
            s = summary[tag]
            lines.append(f"| {tag} | {s['title']} | {s['total']} | {s['pass']} | "
                         f"{s['fail']} | {s['skip']} |")
    lines += ["", "说明：S01–S24 覆盖 Phase5-1 集成验收的 24 类业务场景；",
              "全部使用合成夹具；不触碰 Phase4 历史模型与 Gold 盲测数据（S24 校验）。",
              "严禁跳过失败测试或降低既有门禁标准。", ""]
    (out_dir / "test-results.md").write_text("\n".join(lines), encoding="utf-8",
                                             newline="\n")
    print(f"=== 测试完成 {seconds}s | PASS={out['totals']['pass']} "
          f"FAIL={out['totals']['fail']} SKIP={out['totals']['skip']} | ok={ok} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
