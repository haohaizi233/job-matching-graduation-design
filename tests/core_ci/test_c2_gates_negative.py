# -*- coding: utf-8 -*-
"""C2：Batch 0 可信 CI 门禁的**负向测试**。

纪律：每个新门禁都必须有"违规时确实会失败"的证据，否则门禁本身不可信。
覆盖：
  * 完整性检查器退出码语义（PASS=0 / FAIL=1 / NOT_RUN=0 且不计 PASS）；
  * 合成冻结夹具自检（检查器自身可信）；
  * 运行身份与报告新鲜度（旧报告冒充本次成功必须被拒）；
  * 模型兼容诊断：无 checkpoint 记 NOT_RUN；失败时不留可误读的旧报告；
  * Artifact-dependent 状态登记：NOT_RUN / BLOCKED / ENV_INCOMPATIBLE 不计入 PASS。

所有被测脚本都在**临时目录**内执行，绝不改写仓库里的历史报告。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ROOT / "scripts" / "phase5_1a"
for _p in (str(HERE), str(SCRIPTS), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import run_identity as _ri  # noqa: E402  (scripts/phase5_1a 已加入 sys.path)


def _py() -> str:
    return sys.executable


def _run(args: list[str], env: dict | None = None, cwd: Path | None = None,
         timeout: int = 300) -> tuple[int, str]:
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    if env:
        e.update(env)
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=e,
                       cwd=str(cwd or ROOT))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _make_freeze(root: Path, *, tamper: bool = False, extra_file: bool = False,
                 name: str = "freeze_v1") -> Path:
    """构造一份合成冻结夹具（manifest + 数据文件），用于自检完整性检查器。"""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    files = {}
    for i, payload in enumerate((b"alpha-data", b"beta-data", b"gamma-data")):
        p = d / f"part_{i}.jsonl"
        p.write_bytes(payload)
        files[f"part_{i}"] = {"path": f"part_{i}.jsonl",
                              "sha256": hashlib.sha256(payload).hexdigest()}
    manifest = {"stage": "synthetic-freeze", "dataset_version": "dv-synth-0001",
                "frozen_at": "2026-01-01T00:00:00", "files": files}
    if tamper:
        # 内容与哈希不符 -> 必须 FAIL
        (d / "part_1.jsonl").write_bytes(b"beta-data-TAMPERED")
    if extra_file:
        (d / "unlisted.txt").write_bytes(b"not registered")
    (d / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                     encoding="utf-8", newline="\n")
    return d


# ============================================================ 完整性检查器
class C2ArtifactIntegrityGates(unittest.TestCase):

    def _integrity(self, root: Path, *extra: str) -> tuple[int, dict, str]:
        out = root / "integrity-report.json"
        args = [_py(), str(SCRIPTS / "check_artifact_integrity.py"),
                "--root", str(root), "--glob", "**/manifest*.json",
                "--out", str(out), "--run-id", "selftest-run", *extra]
        code, text = _run(args)
        data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        return code, data, text

    def test_complete_manifest_is_pass_and_exit_zero(self):
        with tempfile.TemporaryDirectory(prefix="jm_freeze_") as td:
            root = Path(td)
            _make_freeze(root)
            code, data, text = self._integrity(root, "--require-manifest")
            self.assertEqual(code, 0, text)
            self.assertEqual(data["status"], "PASS")
            self.assertEqual(data["manifests_ok"], data["manifests_checked"])
            self.assertEqual(data["manifests_checked"], 1)

    def test_tampered_manifest_content_is_fail_and_nonzero(self):
        with tempfile.TemporaryDirectory(prefix="jm_freeze_") as td:
            root = Path(td)
            _make_freeze(root, tamper=True)
            code, data, text = self._integrity(root, "--require-manifest")
            self.assertEqual(code, 1, f"manifest 内容错误必须非零退出: {text}")
            self.assertEqual(data["status"], "FAIL")
            self.assertTrue(data["results"][0]["problems"])
            self.assertIn("哈希不匹配", " ".join(data["results"][0]["problems"]))

    def test_unlisted_file_is_fail(self):
        with tempfile.TemporaryDirectory(prefix="jm_freeze_") as td:
            root = Path(td)
            _make_freeze(root, extra_file=True)
            code, data, _ = self._integrity(root, "--require-manifest")
            self.assertEqual(code, 1)
            self.assertEqual(data["status"], "FAIL")
            self.assertTrue(data["results"][0]["unlisted_files"])

    def test_missing_manifest_when_required_is_fail(self):
        with tempfile.TemporaryDirectory(prefix="jm_freeze_") as td:
            root = Path(td)
            code, data, text = self._integrity(root, "--require-manifest")
            self.assertEqual(code, 1,
                             f"要求必须存在 manifest 但扫描为 0 必须 FAIL: {text}")
            self.assertEqual(data["status"], "FAIL")
            self.assertIn("扫描结果为 0", data["status_reason"])

    def test_missing_manifest_when_optional_is_not_run_never_pass(self):
        with tempfile.TemporaryDirectory(prefix="jm_freeze_") as td:
            root = Path(td)
            code, data, _ = self._integrity(root)
            self.assertEqual(code, 0)
            self.assertEqual(data["status"], "NOT_RUN")
            self.assertNotEqual(data["status"], "PASS",
                                "非必需 artifact 校验且无产物必须显式 NOT_RUN")

    def test_corrupt_manifest_json_is_fail(self):
        with tempfile.TemporaryDirectory(prefix="jm_freeze_") as td:
            root = Path(td)
            d = _make_freeze(root)
            (d / "manifest.json").write_text("{ not json", encoding="utf-8")
            code, data, _ = self._integrity(root, "--require-manifest")
            self.assertEqual(code, 1)
            self.assertEqual(data["status"], "FAIL")

    def test_report_carries_run_identity(self):
        with tempfile.TemporaryDirectory(prefix="jm_freeze_") as td:
            root = Path(td)
            _make_freeze(root)
            _, data, _ = self._integrity(root, "--require-manifest")
            ident = data["run_identity"]
            for key in ("run_id", "git_commit", "execution_time", "python_version",
                        "dependency_versions", "artifact_count", "status"):
                self.assertIn(key, ident, f"运行身份缺少字段 {key}")
            self.assertEqual(ident["artifact_count"], 1)

    def test_decide_status_matrix(self):
        """状态判定单一事实来源的完整矩阵（负向覆盖）。"""
        from check_artifact_integrity import decide_status
        self.assertEqual(decide_status(require_manifest=False, manifest_count=0,
                                       bad_count=0)[0], "NOT_RUN")
        self.assertEqual(decide_status(require_manifest=True, manifest_count=0,
                                       bad_count=0)[0], "FAIL")
        self.assertEqual(decide_status(require_manifest=True, manifest_count=2,
                                       bad_count=0)[0], "PASS")
        self.assertEqual(decide_status(require_manifest=False, manifest_count=2,
                                       bad_count=1)[0], "FAIL")
        self.assertEqual(decide_status(require_manifest=True, manifest_count=2,
                                       bad_count=2)[0], "FAIL")


# ============================================================ 运行身份
class C2RunIdentityGates(unittest.TestCase):

    def test_build_run_identity_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            _ri.build_run_identity(ROOT, status="SUCCESS")

    def test_report_without_run_identity_is_rejected(self):
        with self.assertRaises(_ri.StaleReportError):
            _ri.assert_report_fresh({"summary": {}}, expect_run_id="x")

    def test_stale_run_id_is_rejected(self):
        report = {"run_identity": _ri.build_run_identity(ROOT, status="PASS")}
        report["run_identity"]["run_id"] = "run-OLD"
        with self.assertRaises(_ri.StaleReportError) as cm:
            _ri.assert_report_fresh(report, expect_run_id="run-NEW")
        self.assertIn("拒绝采信", str(cm.exception))

    def test_stale_commit_is_rejected(self):
        ident = _ri.build_run_identity(ROOT, status="PASS")
        ident["run_id"] = "run-NEW"
        ident["git_commit"] = "0" * 40
        with self.assertRaises(_ri.StaleReportError):
            _ri.assert_report_fresh({"run_identity": ident}, expect_run_id="run-NEW",
                                    expect_commit="1" * 40)

    def test_old_execution_time_is_rejected(self):
        ident = _ri.build_run_identity(ROOT, status="PASS")
        ident["run_id"] = "run-NEW"
        ident["execution_time"] = "2000-01-01T00:00:00Z"
        with self.assertRaises(_ri.StaleReportError):
            _ri.assert_report_fresh({"run_identity": ident}, expect_run_id="run-NEW",
                                    max_age_seconds=60)

    def test_illegal_status_is_rejected(self):
        ident = _ri.build_run_identity(ROOT, status="PASS")
        ident["run_id"] = "run-NEW"
        ident["status"] = "SUCCESS"
        with self.assertRaises(_ri.StaleReportError):
            _ri.assert_report_fresh({"run_identity": ident}, expect_run_id="run-NEW")

    def test_fresh_report_is_accepted(self):
        ident = _ri.build_run_identity(ROOT, status="PASS")
        got = _ri.assert_report_fresh({"run_identity": ident},
                                      expect_run_id=ident["run_id"],
                                      expect_commit=ident["git_commit"])
        self.assertEqual(got["run_id"], ident["run_id"])

    def test_not_run_status_is_recorded_not_pass(self):
        self.assertIn("NOT_RUN", _ri.STATUSES)
        self.assertEqual(_ri.PASSING_STATUSES, ("PASS",))

    def test_verifier_cli_rejects_stale_report(self):
        with tempfile.TemporaryDirectory(prefix="jm_fresh_") as td:
            p = Path(td) / "old-report.json"
            ident = _ri.build_run_identity(ROOT, status="PASS")
            ident["run_id"] = "run-OLD"
            p.write_text(json.dumps({"run_identity": ident}), encoding="utf-8")
            code, text = _run([_py(), str(SCRIPTS / "verify_run_freshness.py"),
                               str(p), "--expect-run-id", "run-NEW",
                               "--expect-commit", "1" * 40],
                              cwd=Path(td))
            self.assertEqual(code, 1, f"旧报告必须被拒: {text}")
            self.assertIn("拒绝采信", text)

    def test_verifier_cli_accepts_fresh_pass(self):
        with tempfile.TemporaryDirectory(prefix="jm_fresh_") as td:
            p = Path(td) / "new-report.json"
            ident = _ri.build_run_identity(ROOT, status="PASS")
            p.write_text(json.dumps({"run_identity": ident}), encoding="utf-8")
            code, text = _run([_py(), str(SCRIPTS / "verify_run_freshness.py"),
                               str(p), "--expect-run-id", ident["run_id"],
                               "--expect-commit", ident["git_commit"]],
                              cwd=Path(td))
            self.assertEqual(code, 0, text)

    def test_verifier_cli_rejects_not_run_by_default(self):
        with tempfile.TemporaryDirectory(prefix="jm_fresh_") as td:
            p = Path(td) / "notrun-report.json"
            ident = _ri.build_run_identity(ROOT, status="NOT_RUN")
            p.write_text(json.dumps({"run_identity": ident}), encoding="utf-8")
            code, text = _run([_py(), str(SCRIPTS / "verify_run_freshness.py"),
                               str(p), "--expect-run-id", ident["run_id"],
                               "--expect-commit", ident["git_commit"]],
                              cwd=Path(td))
            self.assertEqual(code, 1, f"NOT_RUN 不得默认计入 PASS: {text}")

    def test_verifier_cli_allow_status_explicit(self):
        with tempfile.TemporaryDirectory(prefix="jm_fresh_") as td:
            p = Path(td) / "notrun-report.json"
            ident = _ri.build_run_identity(ROOT, status="NOT_RUN")
            p.write_text(json.dumps({"run_identity": ident}), encoding="utf-8")
            code, _ = _run([_py(), str(SCRIPTS / "verify_run_freshness.py"),
                            str(p), "--expect-run-id", ident["run_id"],
                            "--expect-commit", ident["git_commit"],
                            "--allow-status", "PASS,NOT_RUN"], cwd=Path(td))
            self.assertEqual(code, 0)

    def test_missing_run_id_env_blocks_reader(self):
        e = {k: v for k, v in os.environ.items() if k != "JM_RUN_ID"}
        r = subprocess.run([_py(), str(SCRIPTS / "verify_run_freshness.py"),
                            "whatever.json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=e, cwd=str(ROOT))
        self.assertEqual(r.returncode, 2, (r.stdout or "") + (r.stderr or ""))
        self.assertIn("JM_RUN_ID", (r.stdout or "") + (r.stderr or ""))


# ============================================================ 模型兼容诊断
class C2ModelCompatGates(unittest.TestCase):

    def test_no_checkpoint_is_not_run_not_pass(self):
        with tempfile.TemporaryDirectory(prefix="jm_model_") as td:
            root = Path(td)
            out = root / "model-compat.json"
            code, text = _run([_py(), str(SCRIPTS / "diagnose_model_compat.py"),
                               "--root", str(root), "--out", str(out),
                               "--run-id", "mc-run-1"])
            self.assertEqual(code, 0, text)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "NOT_RUN")
            self.assertNotEqual(data["status"], "PASS")
            self.assertEqual(data["models"], [])
            self.assertIn("NOT_RUN", data["status_reason"])
            self.assertEqual(data["run_identity"]["artifact_count"], 0)

    def test_diagnosis_never_reuses_previous_report(self):
        """运行后若崩溃/未产出，仓库里不得留着可被误读的旧报告。"""
        with tempfile.TemporaryDirectory(prefix="jm_model_") as td:
            root = Path(td)
            out = root / "model-compat.json"
            stale = {"run_identity": {"run_id": "run-OLD", "status": "PASS"},
                     "summary": {"loaded": 99}}
            out.write_text(json.dumps(stale), encoding="utf-8")
            code, _ = _run([_py(), str(SCRIPTS / "diagnose_model_compat.py"),
                            "--root", str(root), "--out", str(out),
                            "--run-id", "mc-run-2"])
            self.assertEqual(code, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["run_identity"]["run_id"], "mc-run-2")
            self.assertNotEqual(data["summary"], {"loaded": 99},
                                "旧报告内容被原样保留 = 复用了旧结果")
            self.assertFalse(out.with_suffix(".json.stale").exists(),
                             "临时备份未清理")

    def test_report_carries_full_run_identity(self):
        with tempfile.TemporaryDirectory(prefix="jm_model_") as td:
            root = Path(td)
            out = root / "mc.json"
            _run([_py(), str(SCRIPTS / "diagnose_model_compat.py"),
                  "--root", str(root), "--out", str(out), "--run-id", "mc-run-3"])
            ident = json.loads(out.read_text(encoding="utf-8"))["run_identity"]
            for key in ("run_id", "git_commit", "execution_time", "python_version",
                        "dependency_versions", "artifact_count", "status"):
                self.assertIn(key, ident)

    def test_diagnose_without_run_id_env_refuses(self):
        e = {k: v for k, v in os.environ.items() if k != "JM_RUN_ID"}
        with tempfile.TemporaryDirectory(prefix="jm_model_") as td:
            r = subprocess.run([_py(), str(SCRIPTS / "diagnose_model_compat.py"),
                                "--root", td, "--out", str(Path(td) / "x.json")],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=120, env=e, cwd=str(ROOT))
            self.assertEqual(r.returncode, 2, (r.stdout or "") + (r.stderr or ""))

    def test_manifest_without_weights_is_skipped_not_pass(self):
        with tempfile.TemporaryDirectory(prefix="jm_model_") as td:
            root = Path(td)
            d = root / "models" / "probe" / "run1"
            d.mkdir(parents=True)
            (d / "manifest.json").write_text(json.dumps({"model_name": "probe"}),
                                             encoding="utf-8")
            out = root / "mc.json"
            _run([_py(), str(SCRIPTS / "diagnose_model_compat.py"),
                  "--root", str(root), "--out", str(out), "--run-id", "mc-run-4"])
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["models"][0]["status"], "skipped")
            self.assertEqual(data["status"], "PASS", "诊断确实执行了（对象存在）")


# ============================================================ 状态登记器
class C2ValidationRegistryGates(unittest.TestCase):

    def test_probe_mode_never_reports_pass_for_unrun_checks(self):
        with tempfile.TemporaryDirectory(prefix="jm_reg_") as td:
            out = Path(td) / "registry.json"
            code, text = _run([_py(), str(SCRIPTS / "summarize_validation.py"),
                               "--out", str(out)])
            self.assertEqual(code, 0, text)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn(data["overall"], ("PASS", "INCOMPLETE", "FAIL"))
            for item in data["items"]:
                if not item.get("executed"):
                    self.assertNotEqual(item["status"], "PASS",
                                        f"{item['id']} 未执行却记为 PASS")

    def test_blockers_recorded_as_blocked_not_pass(self):
        with tempfile.TemporaryDirectory(prefix="jm_reg_") as td:
            out = Path(td) / "registry.json"
            _run([_py(), str(SCRIPTS / "summarize_validation.py"), "--out", str(out)])
            data = json.loads(out.read_text(encoding="utf-8"))
            by_id = {i["id"]: i for i in data["items"]}
            self.assertEqual(by_id["h2_real_chinese_gold"]["status"], "BLOCKED")
            self.assertEqual(by_id["phase4_3b"]["status"], "BLOCKED")
            self.assertNotIn("h2_real_chinese_gold",
                             [i["id"] for i in data["items"] if i["status"] == "PASS"])

    def test_status_vocabulary_is_closed(self):
        with tempfile.TemporaryDirectory(prefix="jm_reg_") as td:
            out = Path(td) / "registry.json"
            _run([_py(), str(SCRIPTS / "summarize_validation.py"), "--out", str(out)])
            data = json.loads(out.read_text(encoding="utf-8"))
            for item in data["items"]:
                self.assertIn(item["status"], _ri.STATUSES, item["id"])

    def test_registry_rejects_illegal_status(self):
        from summarize_validation import Registry
        reg = Registry()
        with self.assertRaises(ValueError):
            reg.add("x", "t", [], "SUCCESS", "bad")

    def test_counts_do_not_fold_not_run_into_pass(self):
        from summarize_validation import Registry
        reg = Registry()
        reg.add("a", "t", [], "NOT_RUN", "r")
        reg.add("b", "t", [], "BLOCKED", "r")
        c = reg.counts()
        self.assertEqual(c["PASS"], 0)
        self.assertEqual(c["NOT_RUN"], 1)
        self.assertEqual(c["BLOCKED"], 1)

    def test_strict_mode_fails_on_incomplete(self):
        with tempfile.TemporaryDirectory(prefix="jm_reg_") as td:
            out = Path(td) / "registry.json"
            code, _ = _run([_py(), str(SCRIPTS / "summarize_validation.py"),
                            "--strict", "--out", str(out)])
            self.assertEqual(code, 1,
                             "strict 模式下存在非 PASS 必须非零退出")


if __name__ == "__main__":
    unittest.main(verbosity=2)
