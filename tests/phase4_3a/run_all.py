# -*- coding: utf-8 -*-
"""Phase4-3A 评估工程测试运行器（stdlib unittest，不引入 pytest）。

用法:
    python tests/phase4_3a/run_all.py            # 全部测试
    python tests/phase4_3a/run_all.py P9         # 只跑 P9

输出:
    控制台逐项 PASS/FAIL + reports/phase4-3a/test-results.json
    退出码：0 = 全部通过；1 = 存在 FAIL
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
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "phase4_3a"))
sys.path.insert(0, str(HERE))

TEST_MODULES = [
    ("P1", "test_p1_pair_pool", "合法配对生成 / 固定种子复现"),
    ("P2", "test_p2_dedup", "完全重复与近似重复检测"),
    ("P3", "test_p3_leakage", "训练数据与评估数据交叉检测"),
    ("P4", "test_p4_annotation_import", "标注导入校验 / 非法标签拒绝 / 缺失标注"),
    ("P5", "test_p5_agreement", "标注一致性（一致率 / Kappa / Weighted Kappa）"),
    ("P6", "test_p6_arbitration", "双人分歧 / 仲裁结果追踪"),
    ("P7", "test_p7_freeze", "数据冻结 / SHA-256 复验 / 互斥检查"),
    ("P8", "test_p8_metrics", "评估指标正确性 / 小样本与空样本 / 模型缺失"),
    ("P9", "test_p9_bootstrap", "配对 Bootstrap 确定性与稳定性"),
    ("P10", "test_p10_pii", "个人信息脱敏与导出检查"),
    ("P11", "test_p11_intake_consent", "授权门禁 / 中文简历判定 / 合成数据冒充防护"),
    ("P12", "test_p12_pairs", "配对唯一性 / 组级切分隔离 / 训练交叉与近似重复"),
    ("P13", "test_p13_blindness", "盲标视图白名单 / 标注员独立性"),
    ("P14", "test_p14_annotation_integrity", "标签与协议版本校验 / unjudgeable 保护 / 仲裁留痕"),
    ("P15", "test_p15_pii_export", "PII 字段不得进入公开导出"),
    ("P16", "test_p16_freeze_blind", "盲测保护 / 冻结门禁 / SHA-256 复验"),
    ("P17", "test_p17_g2_blocked", "G2 阻断判定 / 合成数据不计入真实 Gold"),
    ("P18", "test_p18_reproducibility", "固定种子可复现输出"),
]


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records: list[dict] = []

    def _group_of(self, test) -> str:
        m = re.match(r"^P(\d+)", type(test).__name__)
        return f"P{m.group(1)}" if m else "P?"

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


def main() -> int:
    only = sys.argv[1].upper() if len(sys.argv) > 1 else ""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for tag, mod, _title in TEST_MODULES:
        if only and tag != only:
            continue
        suite.addTests(loader.loadTestsFromName(mod))

    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    t0 = time.time()
    result = runner.run(suite)
    seconds = round(time.time() - t0, 2)

    records = result.records
    summary = {}
    for tag, mod, title in TEST_MODULES:
        rows = [r for r in records if r["group"] == tag]
        if not rows:
            continue
        summary[tag] = {
            "title": title,
            "total": len(rows),
            "pass": sum(1 for r in rows if r["status"] == "PASS"),
            "fail": sum(1 for r in rows if r["status"] in ("FAIL", "ERROR")),
            "skip": sum(1 for r in rows if r["status"] == "SKIP"),
        }
    ok = not (result.failures or result.errors)
    out = {
        "generated_by": "tests/phase4_3a/run_all.py",
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
    out_dir = ROOT / "reports" / "phase4-3a"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "test-results.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Phase4-3A-2 交付：JSON + Markdown 双报告（与 phase4-3a 同内容、独立留档）
    out2 = ROOT / "reports" / "phase4-3a-2"
    out2.mkdir(parents=True, exist_ok=True)
    with open(out2 / "test-results.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    lines = [
        "# Phase4-3A-2 自动化测试报告", "",
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
    lines += ["", "说明：P1–P10 为 Phase4-3A 既有 157 项测试（只扩展不重写）；",
              "P11–P18 为 Phase4-3A-2 新增门禁场景测试。",
              "严禁跳过失败测试或降低旧门禁标准。", ""]
    (out2 / "test-results.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"=== 测试完成 {seconds}s | PASS={out['totals']['pass']} "
          f"FAIL={out['totals']['fail']} SKIP={out['totals']['skip']} | ok={ok} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
