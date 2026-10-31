# -*- coding: utf-8 -*-
"""C5：Core CI 契约（证明 Core CI 真的不需要真实数据 / 权重 / GPU / 网络下载）。

覆盖：
  * 干净 checkout 导出清单里不得出现 data/raw、models/**权重、data/private；
  * Core CI 工作流不得执行依赖真实数据的套件（data_pipeline 全量 / model_training /
    education_training / environment GPU 探测）；
  * Core CI 工作流不得包含任何下载数据集的命令；
  * 模型兼容检查不得用"报告文件存在"冒充本次成功；
  * Core CI 的每个步骤都必须是登记过的可移植套件；
  * Artifact-dependent 检查必须在独立 job 登记，且状态口径合法。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT / "src"), str(ROOT / "scripts" / "phase5_1a")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

WORKFLOW = ROOT / ".github" / "workflows" / "quality-gates.yml"

# 依赖真实数据 / 权重 / GPU 的套件，禁止出现在 Core CI 步骤里
ARTIFACT_ONLY_SUITE_TOKENS = (
    "tests/data_pipeline/run_all.py",      # G1~G7 需要真实 data/raw 与处理产物
    "tests/model_training/run_all.py",     # 需要真实特征与权重
    "tests/education_training/run_all.py",  # 需要真实学历数据
    "tests/environment/test_gpu_training.py",
    "tests/environment/test_torch_cuda.py",
    "tests/environment/test_dataset_loading.py",
)

DOWNLOAD_TOKENS = (
    "wget ", "curl -O", "curl -L -o", "huggingface-cli download",
    "load_dataset(", "snapshot_download(", "git clone ",
    "pip download", "aria2c",
)

# Core CI 允许执行的可移植套件
PORTABLE_SUITE_TOKENS = (
    "tests/phase5_1r/run_all.py",
    "tests/phase5_1a/run_all.py",
    "tests/phase5_1/run_all.py",
    "tests/core_ci/run_all.py",
    "tests/data_pipeline/test_g0_synth_data_quality.py",
)


def _wf_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _core_job_block(text: str) -> str:
    """粗粒度取 core-ci job 的 YAML 块（到下一个顶级 job 为止）。"""
    m = re.search(r"(?m)^  core-ci:\s*$", text)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"(?m)^  [a-zA-Z0-9_-]+:\s*$", rest)
    return rest[:nxt.start()] if nxt else rest


def _artifact_job_block(text: str) -> str:
    m = re.search(r"(?m)^  artifact-dependent-validation:\s*$", text)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"(?m)^  [a-zA-Z0-9_-]+:\s*$", rest)
    return rest[:nxt.start()] if nxt else rest


class C5WorkflowContract(unittest.TestCase):

    def test_workflow_exists(self):
        self.assertTrue(WORKFLOW.exists(), "质量门禁工作流缺失")

    def test_core_ci_job_declared(self):
        self.assertIn("core-ci:", _wf_text(), "缺少 core-ci job")

    def test_artifact_validation_job_declared(self):
        self.assertIn("artifact-dependent-validation:", _wf_text(),
                      "缺少 artifact-dependent-validation job")

    def test_core_ci_runs_portable_suites(self):
        block = _core_job_block(_wf_text())
        self.assertTrue(block.strip(), "无法解析 core-ci job 块")
        for token in PORTABLE_SUITE_TOKENS:
            self.assertIn(token, block, f"core-ci 缺少可移植套件步骤: {token}")

    def test_core_ci_never_runs_artifact_only_suites(self):
        block = _core_job_block(_wf_text())
        offenders = [t for t in ARTIFACT_ONLY_SUITE_TOKENS if t in block]
        self.assertEqual(offenders, [],
                         f"core-ci 不得执行依赖真实数据的套件: {offenders}")

    def test_core_ci_contains_no_download_commands(self):
        text = _wf_text()
        offenders = [t for t in DOWNLOAD_TOKENS if t in text]
        self.assertEqual(offenders, [],
                         f"CI 中不得出现下载数据集/权重的命令: {offenders}")

    def test_core_ci_does_not_greet_stale_model_report(self):
        """禁止 `|| true` + 只检查报告存在 这种假通过模式。"""
        text = _wf_text()
        self.assertNotIn("|| true", text, "CI 不得用 `|| true` 吞掉失败")
        bad = re.findall(r"if not .*exists\(\).*[Mm]odel[-_ ]?compat", text)
        self.assertEqual(bad, [], "不得用'报告存在'冒充模型兼容诊断成功")

    def test_artifact_job_reports_explicit_status(self):
        block = _artifact_job_block(_wf_text())
        self.assertTrue(block.strip(), "无法解析 artifact-dependent-validation job 块")
        self.assertIn("summarize_validation.py", block)
        for word in ("PASS", "FAIL", "BLOCKED", "NOT_RUN", "ENV_INCOMPATIBLE"):
            self.assertIn(word, block, f"状态口径缺少 {word}")

    def test_artifact_job_is_not_required_for_core(self):
        block = _core_job_block(_wf_text())
        self.assertNotIn("needs:", block, "core-ci 不得依赖 artifact-dependent-validation")

    def test_core_ci_writes_run_identity(self):
        block = _core_job_block(_wf_text())
        self.assertIn("JM_RUN_ID", block, "core-ci 必须建立运行身份 JM_RUN_ID")

    # -------- 完整性检查器调用契约（Phase6 M0）--------
    # 背景：workflow 曾用 `--root data/independent_eval` 调用 check_artifact_integrity.py，
    # 而 manifest 内登记的是**项目根相对路径**，导致全部文件被判「文件缺失」。
    # 该缺陷长期未被发现，是因为 core-ci 前置步骤先失败、后续步骤被 skip。

    @staticmethod
    def _integrity_invocations(text: str) -> list[str]:
        blocks = []
        for m in re.finditer(r"check_artifact_integrity\.py", text):
            seg = text[m.end(): m.end() + 600].split("\n\n", 1)[0]
            blocks.append(seg)
        return blocks

    @staticmethod
    def _run_integrity(scan_root: Path, out: Path) -> tuple[int, str]:
        args = [sys.executable, str(ROOT / "scripts" / "phase5_1a" /
                                    "check_artifact_integrity.py"),
                "--root", str(scan_root), "--glob", "**/manifest*.json",
                "--require-manifest", "--run-id", "selftest-c5", "--out", str(out)]
        r = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180,
                           env=dict(__import__("os").environ, PYTHONUTF8="1"))
        return r.returncode, (r.stdout or "") + (r.stderr or "")

    def test_artifact_integrity_invocation_requires_manifest(self):
        blocks = self._integrity_invocations(_wf_text())
        self.assertTrue(blocks, "workflow 未调用 check_artifact_integrity.py")
        for b in blocks:
            self.assertIn("--require-manifest", b,
                          f"完整性校验必须声明必需 manifest（否则 0 份会被记成 NOT_RUN）: {b!r}")
            self.assertIn("--out", b, f"完整性校验必须显式指定报告输出路径: {b!r}")

    def test_artifact_integrity_root_is_project_root(self):
        """`--root` 必须是项目根，manifest 内的项目根相对路径才能解析到真实文件。"""
        for b in self._integrity_invocations(_wf_text()):
            self.assertNotIn("--root data/independent_eval", b,
                             "check_artifact_integrity.py 的 --root 指向 data/independent_eval "
                             "会把 manifest 内的项目根相对路径解析到 "
                             "data/independent_eval/data/independent_eval/... 并误判「文件缺失」")
            self.assertNotIn("--root data\\independent_eval", b, "同上（Windows 分隔符）")

    def test_integrity_checker_resolves_project_root_relative_paths(self):
        """功能验证：项目根相对路径在 `--root`=项目根 时可解析，指向子目录时确实会失败。"""
        import hashlib
        import tempfile
        with tempfile.TemporaryDirectory(prefix="jm_c5_integrity_") as td:
            proj = Path(td)
            pool = proj / "data" / "independent_eval" / "pool"
            pool.mkdir(parents=True)
            payload = b'{"job_id": "J1", "title": "demo"}\n'
            (pool / "job_pool_v1.jsonl").write_bytes(payload)
            frozen = proj / "data" / "independent_eval" / "frozen" / "pool_v1"
            frozen.mkdir(parents=True)
            manifest = {
                "stage": "pool",
                "files": {"job_pool": {
                    "path": "data/independent_eval/pool/job_pool_v1.jsonl",
                    "sha256": hashlib.sha256(payload).hexdigest()}},
            }
            (frozen / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8", newline="\n")

            ok_code, ok_out = self._run_integrity(proj, proj / "ok.json")
            bad_code, bad_out = self._run_integrity(
                proj / "data" / "independent_eval", proj / "bad.json")
        self.assertEqual(ok_code, 0, f"--root=项目根 应当 PASS: {ok_out[-800:]}")
        self.assertEqual(bad_code, 1,
                         f"--root=子目录 应当 FAIL（证明路径解析契约确实生效）: {bad_out[-800:]}")
        self.assertIn("文件缺失", bad_out,
                      f"子目录 root 的失败原因应为「文件缺失」，而非其它: {bad_out[-800:]}")


class C5CleanCheckoutContract(unittest.TestCase):

    def test_file_list_source_is_explicitly_registered(self):
        """文件清单来源必须显式登记：git 与无 git 退化路径不得互相冒充。"""
        import verify_fresh_checkout as vfc
        files = vfc.tracked_file_list()
        self.assertTrue(files, "无法取得文件清单")
        src = vfc.file_list_source()
        self.assertIn(src, (vfc.SOURCE_GIT, vfc.SOURCE_FALLBACK),
                      f"未知的文件清单来源: {src}")
        if src == vfc.SOURCE_FALLBACK:
            # 退化枚举只在"已导出的干净 checkout / 源码包"中才可信；
            # 若在真实开发仓库根（git 可用）却退化，说明清单来源被伪装，
            # 直接判失败，绝不把退化结果冒充 git 权威清单。
            self.assertFalse(vfc._git_available(),
                             "git 可用却走了退化枚举，来源登记不可信")

    def test_clean_export_has_no_forbidden_artifacts(self):
        """干净 checkout 导出清单里不得出现 data/raw、data/private、models/** 权重。

        Phase6 口径：训练产物允许入库（models/ 是交付物），但导出到干净 checkout
        时**仍被剥离**，以证明 Core CI 不依赖真实数据 / 权重即可运行。
        """
        import tempfile
        import verify_fresh_checkout as vfc
        with tempfile.TemporaryDirectory(prefix="jm_c5_export_") as td:
            copied = vfc.export_clean_checkout(Path(td))
            self.assertTrue(copied, "无法导出干净 checkout 文件清单")
            bad = vfc.assert_no_forbidden_artifacts(Path(td))
        self.assertEqual(
            bad, [],
            "干净 checkout 导出含被禁产物（导出必须剥离 data/raw、data/private、"
            f"models/** 权重）: {bad[:8]}")

    def test_clean_export_contains_portable_suite_sources(self):
        import verify_fresh_checkout as vfc
        files = set(vfc.tracked_file_list())
        for must in ("tests/core_ci/run_all.py",
                     "tests/data_pipeline/test_g0_synth_data_quality.py",
                     "tests/data_pipeline/synth_fixtures.py",
                     "scripts/phase5_1a/check_artifact_integrity.py",
                     "scripts/phase5_1a/run_identity.py"):
            self.assertIn(must, files, f"干净 checkout 缺少 {must}")

    def test_synthetic_fixtures_are_declared_synthetic(self):
        p = ROOT / "tests/data_pipeline/synth_fixtures.py"
        text = p.read_text(encoding="utf-8")
        self.assertIn("synthetic", text.lower())
        self.assertIn("tempfile", text, "合成夹具必须写入临时目录")

    def test_config_supports_data_root_override(self):
        import os
        from job_matching import config as _c
        try:
            os.environ["JM_DATA_ROOT"] = str(ROOT / "_probe_root_xyz")
            _c.reset_config()
            cfg = _c.get_config()
            self.assertEqual(cfg.root, (ROOT / "_probe_root_xyz").resolve())
            self.assertEqual(cfg.out("processed_matching"),
                             cfg.root / "data" / "processed" / "matching")
            self.assertEqual(cfg.src("matching", "matches"),
                             cfg.root / "data" / "raw" / "job-resume-matching" / "matches.csv")
            # 配置文件本身不随数据根重定向
            self.assertTrue(cfg.pipeline)
        finally:
            os.environ.pop("JM_DATA_ROOT", None)
            _c.reset_config()
        cfg2 = _c.get_config()
        self.assertEqual(cfg2.root, _c.ROOT, "默认行为必须与历史一致")

    def test_registry_gate_report_schema(self):
        """状态口径登记表的 schema 必须固定，便于 CI 消费。"""
        from run_identity import STATUSES
        self.assertEqual(sorted(STATUSES),
                         ["BLOCKED", "ENV_INCOMPATIBLE", "FAIL", "NOT_RUN", "PASS"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
