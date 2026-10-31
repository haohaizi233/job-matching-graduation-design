# -*- coding: utf-8 -*-
"""P10 隐私与冻结守卫：导出脱敏 / 日志不落简历原文 / 冻结数据不可修改。

冻结相关测试使用临时目录中的合成夹具（明确标记，不进入 Gold），
验证的是**工具链行为**，不代表真实 H2 已完成。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.annotation.freeze import (  # noqa: E402
    FreezeError, freeze_dataset, verify_freeze)
from job_matching.annotation.pii import (  # noqa: E402
    check_export, detect_pii, mask_matches, pii_field_violations, scrub_record)

PAIRS_FIXTURE = ROOT / "data/independent_eval/pairs/pairs_synthetic_v1.jsonl"
FROZEN_DIR = ROOT / "data/independent_eval/frozen"
REPORT_DIRS = (ROOT / "reports/phase4-3b", ROOT / "reports/model-research")


def _sample_pairs(n: int = 5) -> list[dict]:
    rows = []
    with open(PAIRS_FIXTURE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
            if len(rows) >= n:
                break
    return rows


def _write_jsonl(rows: list[dict], path: Path) -> Path:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


class P10PrivacyGuards(unittest.TestCase):
    # ---------------- PII 检测 / 脱敏
    def test_detect_pii_finds_phone_and_id(self):
        text = "联系电话：13812345678，身份证号：110101199001011234"
        hits = detect_pii(text)
        self.assertGreater(sum(hits.values()), 0, "明文手机号/身份证必须被检出")

    def test_mask_matches_removes_pii(self):
        text = "联系电话：13812345678"
        masked = mask_matches(text)
        self.assertNotIn("13812345678", masked)
        residual = [k for k, v in detect_pii(masked).items() if v]
        self.assertEqual([], residual, "脱敏后不得残留 PII 命中")

    def test_scrub_record_redacts_pii_fields(self):
        rec = {"summary": "联系我 13812345678", "phone": "13812345678"}
        scrubbed, _stats = scrub_record(rec, fields=("summary",))
        self.assertNotIn("13812345678", scrubbed["summary"])

    def test_pii_field_names_blocked_in_export(self):
        rec = {"phone": "13812345678", "summary": "无 PII 文本"}
        self.assertTrue(pii_field_violations(rec), "PII 结构化字段名禁止导出")
        problems = check_export(rec, text_fields=("summary",))
        self.assertTrue(any("禁止导出" in p for p in problems))

    def test_check_export_blocks_unmasked_text(self):
        rec = {"summary": "电话 13812345678"}
        problems = check_export(rec, text_fields=("summary",))
        self.assertTrue(problems, "未脱敏文本不得通过导出检查")
        clean = {"summary": mask_matches(rec["summary"])}
        self.assertEqual([], check_export(clean, text_fields=("summary",)))

    def test_check_export_whitelist_enforced(self):
        rec = {"summary": "干净文本", "internal_note": "内部字段"}
        problems = check_export(rec, text_fields=("summary",), allowed_columns=("summary",))
        self.assertTrue(any("白名单" in p for p in problems))

    # ---------------- 报告产物不得落简历原文
    def test_reports_do_not_contain_raw_resume_text(self):
        samples = [r.get("resume_text", "") for r in _sample_pairs(3)]
        samples = [s for s in samples if len(s) >= 20]
        self.assertGreater(len(samples), 0, "合成夹具应含 resume_text 样本")
        checked = 0
        for d in REPORT_DIRS:
            if not d.exists():
                continue
            for p in d.rglob("*.json"):
                text = p.read_text(encoding="utf-8", errors="ignore")
                for s in samples:
                    self.assertNotIn(s, text, f"{p} 中出现简历原文（违反隐私纪律）")
                checked += 1
            for p in d.rglob("*.md"):
                text = p.read_text(encoding="utf-8", errors="ignore")
                for s in samples:
                    self.assertNotIn(s, text, f"{p} 中出现简历原文（违反隐私纪律）")
                checked += 1
        self.assertGreater(checked, 0, "应实际扫描到报告产物")

    # ---------------- 冻结工具链
    def test_frozen_gold_not_claimed(self):
        """正式 Gold 未冻结是既定事实：
        evalset_* 目录不得出现成功冻结的 manifest.json（H2 仍为 BLOCKED）；
        pool_* 是岗位池冻结（非 Gold），允许存在 manifest，但必须可复验且不可改。
        """
        self.assertTrue(FROZEN_DIR.exists())
        seen_evalset = seen_pool = 0
        for d in sorted(FROZEN_DIR.iterdir()):
            if not d.is_dir():
                continue
            if d.name.startswith("evalset"):
                seen_evalset += 1
                self.assertFalse((d / "manifest.json").exists(),
                                 f"{d.name} 不得存在成功冻结的 manifest（H2 仍为 BLOCKED）")
                blocked = d / "freeze_blocked.json"
                self.assertTrue(blocked.exists(), f"{d.name} 必须留下阻断记录")
                rec = json.loads(blocked.read_text(encoding="utf-8"))
                self.assertEqual("blocked", rec.get("status"))
                reason = rec.get("reason") or rec.get("reasons")
                self.assertTrue(reason, "阻断必须写明原因")
            elif d.name.startswith("pool"):
                seen_pool += 1
                manifest = d / "manifest.json"
                if manifest.exists():
                    rec = json.loads(manifest.read_text(encoding="utf-8"))
                    self.assertNotEqual("evalset", rec.get("stage"),
                                        "pool 冻结不得冒充人工真值评估集")
                    res = verify_freeze(manifest)
                    self.assertTrue(res["ok"],
                                    f"{d.name} 冻结产物被改动或哈希不一致: {res['files']}")
        self.assertGreaterEqual(seen_evalset, 1, "应存在 evalset 冻结目录")
        self.assertGreaterEqual(seen_pool, 1, "应存在 pool 冻结目录")

    def _freeze_pool(self, root: Path, dataset_version: str):
        pairs = _write_jsonl(_sample_pairs(5), root / "pairs.jsonl")
        out_dir = root / "pool_freeze"
        manifest = freeze_dataset(
            stage="pool", out_dir=out_dir, pairs_file=pairs,
            files={"pairs": pairs}, dataset_version=dataset_version,
            path_map={"pairs": pairs},
            source_stats={"rows": 5, "note": "unit-test synthetic fixture"})
        return pairs, out_dir, manifest

    def test_pool_freeze_then_verify_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pairs, out_dir, manifest = self._freeze_pool(root, "ut-pool-dv-001")
            self.assertTrue((out_dir / "manifest.json").exists())
            res = verify_freeze(out_dir / "manifest.json")
            self.assertTrue(res["ok"], f"冻结后立即复验应通过: {res['files']}")
            self.assertEqual("ut-pool-dv-001", res["dataset_version"])

    def test_frozen_files_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pairs, out_dir, _m = self._freeze_pool(root, "ut-pool-dv-002")
            with open(pairs, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"pair_id": "tampered", "is_synthetic": True},
                                   ensure_ascii=False) + "\n")
            res = verify_freeze(out_dir / "manifest.json")
            self.assertFalse(res["ok"], "冻结后文件被改动必须被复验发现")

    def test_freeze_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _pairs, out_dir, _m = self._freeze_pool(root, "ut-pool-dv-003")
            with self.assertRaises(FreezeError):
                self._freeze_pool(root, "ut-pool-dv-003")

    def test_freeze_refuses_same_dataset_version_twice(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._freeze_pool(root, "ut-pool-dv-004")
            pairs = _write_jsonl(_sample_pairs(5), root / "pairs2.jsonl")
            with self.assertRaises(FreezeError):
                freeze_dataset(
                    stage="pool", out_dir=root / "pool_freeze_2", pairs_file=pairs,
                    files={"pairs": pairs}, dataset_version="ut-pool-dv-004",
                    path_map={"pairs": pairs}, source_stats={"rows": 5})

    def test_evalset_freeze_rejects_synthetic_pairs(self):
        """合成配对混入人工真值评估集 -> 冻结拒绝（内容级硬检查）。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pairs = _write_jsonl(_sample_pairs(5), root / "pairs.jsonl")
            with self.assertRaises(FreezeError) as ctx:
                freeze_dataset(
                    stage="evalset", out_dir=root / "evalset_freeze", pairs_file=pairs,
                    files={"pairs": pairs}, dataset_version="ut-eval-dv-001",
                    path_map={"pairs": pairs}, source_stats={"rows": 5},
                    annotation_quality={
                        "annotation_status": "complete", "open_disagreements": 0,
                        "unjudgeable_forced": 0, "synthetic_pairs_included": 0,
                        "arbitration_status": "completed"},
                    responsibility={"note": "unit-test"})
            self.assertIn("合成", str(ctx.exception))

    def test_evalset_freeze_requires_complete_annotation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pairs = _write_jsonl([], root / "pairs.jsonl")
            with self.assertRaises(FreezeError) as ctx:
                freeze_dataset(
                    stage="evalset", out_dir=root / "evalset_freeze", pairs_file=pairs,
                    files={"pairs": pairs}, dataset_version="ut-eval-dv-002",
                    source_stats={"rows": 0},
                    annotation_quality={"annotation_status": "in_progress"},
                    responsibility={"note": "unit-test"})
            self.assertIn("annotation_status", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
