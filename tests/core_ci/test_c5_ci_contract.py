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
            # 若在真实开发仓库根（含 data/raw、models）退化，结果必然包含被禁产物，
            # 下面的 test_clean_export_has_no_forbidden_artifacts 会如实失败（不静默通过）。
            self.assertFalse(vfc._git_available(),
                             "git 可用却走了退化枚举，来源登记不可信")

    def test_clean_export_has_no_forbidden_artifacts(self):
        import verify_fresh_checkout as vfc
        files = vfc.tracked_file_list()
        self.assertTrue(files, "无法取得文件清单")
        bad = [f for f in files
               if f.startswith(vfc.FORBIDDEN_PREFIXES) or f.endswith(vfc.FORBIDDEN_SUFFIXES)]
        self.assertEqual(
            bad, [],
            "干净 checkout 含被禁产物（若本机不在 git 仓库内，无法证明 checkout 洁净，"
            f"请在 git 仓库中运行）: {bad[:8]}")

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
