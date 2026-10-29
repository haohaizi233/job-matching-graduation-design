# -*- coding: utf-8 -*-
"""R1：Gold 冻结循环门禁修复回归（Phase5-1R F-001，兼 F-003/F-004 的 CLI 链路）。

业务不变量：
  * Pre-freeze Gate **不得**要求任何冻结哈希/切分结果（否则形成
    「未冻结 -> 不过门禁 -> 不能冻结」循环依赖，真实数据到位也进不了成功路径）；
  * Post-freeze Gate 负责切分隔离 / 唯一性 / 标签 / 文件 / SHA-256 / 版本 / 来源；
  * 任意关键检查失败都必须拒绝最终 PASS；
  * 工程夹具只证明冻结软件流程可运行，绝不产生真实 H2 PASS；
  * 测试全程不触碰真实 Gold 目录与历史模型（前后指纹校验）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import _util as U

from job_matching.annotation import gold_gate


def full_precheck_facts(**over) -> dict:
    """满足冻结前置条件的最小事实集（strict=True 口径）。"""
    facts = {
        "consent_complete": True,
        "source_license_ok": True,
        "real_resumes": 3,
        "real_pairs": 4,
        "dual_annotation_complete": True,
        "annotator_independence_ok": True,
        "open_disagreements": 0,
        "arbitration_status": "not_required",
        "unjudgeable_forced": 0,
        "blocking_findings": [],
        "synthetic_pairs_included": 0,
    }
    facts.update(over)
    return facts


def full_postcheck_facts(**over) -> dict:
    facts = {
        "split_isolation_ok": True,
        "pair_id_unique": True,
        "resume_job_unique": True,
        "final_labels_complete": True,
        "final_labels_unique": True,
        "final_label_pairs_known": True,
        "files_complete": True,
        "sha256_ok": True,
        "dataset_version_ok": True,
        "provenance_complete": True,
        "freeze_verified": True,
    }
    facts.update(over)
    return facts


class R1PreFreezeGate(unittest.TestCase):
    """F-001 核心回归：冻结前置检查不得依赖冻结结果。"""

    def test_precheck_does_not_require_freeze_hash(self):
        # 修复前：facts 里 split_isolation_ok=False / freeze_verified=False 会
        # 直接挡住 G2，而这两个事实恰好产生于本次检查之后（循环依赖）。
        facts = full_precheck_facts()
        self.assertNotIn("freeze_verified", facts)
        self.assertNotIn("split_isolation_ok", facts)
        pre = gold_gate.evaluate_precheck(facts, min_real_pairs=4, strict=True)
        self.assertTrue(pre["precheck_passed"], pre["reasons"])
        self.assertEqual(pre["status"], "ready")

    def test_precheck_blocks_when_data_incomplete(self):
        for over, keyword in (
            ({"real_pairs": 0}, "真实有效配对"),
            ({"real_resumes": 0}, "真实中文简历"),
            ({"dual_annotation_complete": False}, "双人独立标注"),
            ({"annotator_independence_ok": False}, "独立性"),
            ({"open_disagreements": 2}, "分歧"),
            ({"arbitration_status": "pending"}, "仲裁"),
            ({"arbitration_status": "invalid"}, "仲裁记录非法"),
            ({"unjudgeable_forced": 1}, "unjudgeable"),
            ({"blocking_findings": ["泄漏样例"]}, "阻断性"),
            ({"synthetic_pairs_included": 3}, "合成"),
            ({"consent_complete": False}, "授权"),
            ({"source_license_ok": False}, "许可"),
        ):
            with self.subTest(**over):
                pre = gold_gate.evaluate_precheck(full_precheck_facts(**over),
                                                  min_real_pairs=4, strict=True)
                self.assertFalse(pre["precheck_passed"])
                self.assertEqual(pre["status"], "blocked")
                self.assertTrue(any(keyword in r for r in pre["reasons"]),
                                f"{over} 应给出 {keyword} 相关原因: {pre['reasons']}")

    def test_precheck_strict_requires_explicit_facts(self):
        pre = gold_gate.evaluate_precheck({}, min_real_pairs=4, strict=True)
        self.assertFalse(pre["precheck_passed"])
        missing = [k for k, v in pre["checks"].items() if v.get("missing")]
        self.assertTrue(missing, "strict 模式下缺失事实必须登记 missing_fact")

    def test_precheck_enforces_min_real_pairs(self):
        pre = gold_gate.evaluate_precheck(full_precheck_facts(real_pairs=3),
                                          min_real_pairs=300, strict=True)
        self.assertFalse(pre["precheck_passed"])


class R1PostFreezeGate(unittest.TestCase):
    """Post-freeze Gate：任一关键检查失败都必须拒绝最终 PASS。"""

    def test_postcheck_passes_with_full_facts(self):
        post = gold_gate.evaluate_postcheck(full_postcheck_facts(), strict=True)
        self.assertTrue(post["postcheck_passed"], post["reasons"])
        self.assertTrue(post["freeze_verified"])

    def test_postcheck_rejects_each_failed_check(self):
        for key in gold_gate._POSTCHECK_RULES:
            with self.subTest(check=key):
                post = gold_gate.evaluate_postcheck(
                    full_postcheck_facts(**{key: False}), strict=True)
                self.assertFalse(post["postcheck_passed"])
                self.assertEqual(post["status"], "failed")
                self.assertTrue(post["reasons"])

    def test_g2_never_passes_without_postcheck(self):
        g2 = gold_gate.evaluate_g2_status(
            {**full_precheck_facts(), **full_postcheck_facts(sha256_ok=False)},
            min_real_pairs=4, strict=True)
        self.assertEqual(g2["status"], "blocked")
        self.assertTrue(any("哈希" in r or "sha" in r.lower() for r in g2["reasons"]))

    def test_g2_blocked_without_real_data(self):
        g2 = gold_gate.evaluate_g2_status({"real_resumes": 0, "real_pairs": 0},
                                          min_real_pairs=4, strict=True)
        self.assertEqual(g2["status"], "blocked")

    def test_blind_protection_requires_freeze(self):
        res = gold_gate.check_blind_status(freeze_verified=False, blind_claimed_pass=True)
        self.assertFalse(res["ok"])
        self.assertEqual(res["violations"][0]["code"], "blind_pass_before_freeze")


class R1FreezeCliChain(unittest.TestCase):
    """完整 CLI 正向链路（真实脚本 + 隔离工程夹具工作区）。"""

    def setUp(self):
        self._before = U.guard_snapshot()

    def tearDown(self):
        diff = U.diff_snapshots(self._before, U.guard_snapshot())
        self.assertEqual(diff, [], f"测试不得触碰历史资产: {diff}")

    def _fresh(self, n_pairs=8):
        import tempfile
        td = tempfile.TemporaryDirectory(prefix="ph51r_r1_")
        self.addCleanup(td.cleanup)
        ws = U.FixtureWorkspace(Path(td.name), n_pairs=n_pairs)
        return ws

    def test_blocked_without_annotations(self):
        ws = self._fresh()
        ws.build()   # 有合法配对结构，但零人工标注
        rc, res, _ = ws.run_freeze()
        self.assertEqual(rc, 0)
        self.assertEqual(res["status"], "blocked")
        self.assertFalse(res["freeze_written"])
        self.assertFalse(res["freeze_verified"])
        self.assertEqual(res["h2_status"], "blocked")
        self.assertFalse((ws.evalset_dir / "manifest.json").exists(),
                         "门禁不通过时不得留下可被误认为完整冻结的 manifest")
        rep = ws.freeze_report()
        self.assertEqual(rep["status"], "blocked")
        self.assertTrue(rep["reasons"])

    def test_positive_chain_engineering_success(self):
        ws = self._fresh()
        ws.agree_all("1")
        ws.build()
        rc, qa, _ = ws.run_qa()
        self.assertEqual(rc, 0)
        self.assertEqual(qa["annotation_status"], "complete")

        rc, res, _ = ws.run_freeze()
        self.assertEqual(rc, 0)
        self.assertEqual(res["status"], "frozen", res)
        self.assertTrue(res["precheck_passed"])
        self.assertTrue(res["split_validated"])
        self.assertTrue(res["freeze_written"])
        self.assertTrue(res["freeze_verified"])
        self.assertTrue(res["postcheck_passed"])
        # 工程成功 ≠ 真实 H2 PASS
        self.assertEqual(res["h2_status"], "blocked")
        self.assertTrue(res["fixture_mode"])
        self.assertTrue((ws.evalset_dir / "manifest.json").exists())

        manifest = U.jload(ws.evalset_dir / "manifest.json")
        self.assertEqual(manifest["stage"], "evalset")
        self.assertTrue(manifest["dataset_version"])
        self.assertTrue(manifest["manifest_sha256"])
        self.assertIn("responsibility", manifest)
        self.assertTrue(manifest["responsibility"].get("annotators"))

    def test_split_is_resume_group_level(self):
        ws = self._fresh(n_pairs=8)   # 4 份简历，每份 2 对
        ws.agree_all("1")
        ws.build()
        ws.run_qa()
        _, res, _ = ws.run_freeze()
        info = res["split_info"]
        self.assertFalse(set(info["resumes_dev"]) & set(info["resumes_blind"]),
                         "同一简历不得跨 dev_validation / blind_test")
        self.assertEqual(info["pairs_dev"] + info["pairs_blind"] + info["pairs_excluded"],
                         8)

    def test_tamper_detected_on_reverify(self):
        ws = self._fresh()
        ws.agree_all("1")
        ws.build()
        ws.run_qa()
        _, res, _ = ws.run_freeze()
        self.assertTrue(res["freeze_verified"])
        rc, ver, _ = ws.run_verify()
        self.assertEqual(rc, 0)
        self.assertTrue(ver["ok"])

        target = ws.evalset_dir / "pairs_frozen.jsonl"
        with open(target, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"pair_id": "pair-tampered"}, ensure_ascii=False) + "\n")
        rc, ver2, _ = ws.run_verify()
        self.assertEqual(rc, 0)
        self.assertFalse(ver2["ok"], "篡改冻结产物后 SHA-256 复验必须失败")
        self.assertTrue(any(not f["match"] for f in ver2["files"]))

        # 复验失败后 postcheck 不得放行最终 PASS
        post = gold_gate.evaluate_postcheck(full_postcheck_facts(sha256_ok=False),
                                            strict=True)
        self.assertFalse(post["postcheck_passed"])

    def test_fixture_mode_rejected_in_real_workspace(self):
        import os
        env = {k: v for k, v in os.environ.items() if k != "PHASE4_3A_2_WORKSPACE"}
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, str(U.ROOT / "scripts/phase4_3a_2/freeze_gold.py"),
             "--fixture-mode"],
            cwd=str(U.ROOT), capture_output=True, timeout=120, env=env)
        self.assertEqual(proc.returncode, 2, proc.stdout[:500])
        out = proc.stdout.decode("utf-8", errors="replace")
        self.assertIn("隔离工作区", out)

    def test_verify_subcommand_reports_each_file(self):
        ws = self._fresh()
        ws.agree_all("1")
        ws.build()
        ws.run_qa()
        ws.run_freeze()
        _, ver, _ = ws.run_verify()
        keys = {f["key"] for f in ver["files"]}
        for expect in ("pairs", "split_lists", "final_labels", "annotations_a",
                       "annotations_b"):
            self.assertIn(expect, keys)
        for f in ver["files"]:
            self.assertTrue(f["exists"], f)
            self.assertTrue(f["match"], f)


if __name__ == "__main__":
    unittest.main()
