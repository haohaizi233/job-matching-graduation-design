# -*- coding: utf-8 -*-
"""P11 可复现性守卫：仓库根解析可移植 + 工作区行尾与冻结完整性。

背景（本轮实测发现的两个真实缺陷，本模块是它们的回归护栏）：

D1 串仓缺陷：
    `scripts/phase4_3b/*.py` 曾把 `JM_ROOT` 默认值写死为
    `D:\\desktop\\job-matching-model-research`。在别的检出里运行时会静默扫描
    **另一个仓库**的 models/ 与 data/，模型登记串仓、冻结复验失败且极难定位。

D2 行尾完整性缺陷：
    Windows `core.autocrlf=true` 在 checkout 时把 blob 里的 LF smudge 成 CRLF，
    使 `verify_freeze` 的逐字节 SHA-256 误报「冻结产物被改动」。实测 4 个冻结文件
    的 LF 归一化 SHA-256 与 manifest 逐个精确吻合，语义内容完全未变。

纪律：
  * 本模块只读校验，不改写任何仓库文件；
  * 断言失败说明可复现性被破坏，必须修复而不是放宽断言。
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "phase4_3b"))

FROZEN_DIR = ROOT / "data" / "independent_eval" / "frozen"


class P11ReproducibilityGuards(unittest.TestCase):
    # ---------------- D1：仓库根解析
    def test_paths_root_is_this_repo(self):
        import _paths
        self.assertEqual(ROOT.resolve(), _paths.ROOT.resolve(),
                         "_paths.ROOT 必须指向当前检出，而不是别的工作树")
        self.assertTrue((_paths.ROOT / "src" / "job_matching").exists())
        self.assertEqual(_paths.MODELS_ROOT, _paths.ROOT / "models")

    def test_no_hardcoded_absolute_root_in_research_scripts(self):
        """研究脚本不得再写死本机绝对路径作为默认根（D1 缺陷回归护栏）。"""
        forbidden = []
        for py in sorted((ROOT / "scripts" / "phase4_3b").glob("*.py")):
            if py.name == "_paths.py":
                # 只有 _paths.py 允许读取 JM_ROOT：默认值必须为空，
                # 解析后必须走 assert_repo_root 自检（不静默退化）。
                text = py.read_text(encoding="utf-8")
                self.assertIn("assert_repo_root", text)
                self.assertIn('os.environ.get("JM_ROOT", "")', text,
                              "JM_ROOT 默认值必须为空，不得写死本机路径")
                continue
            text = py.read_text(encoding="utf-8", errors="ignore")
            for needle in ("JM_ROOT", "D:\\desktop", "D:/desktop",
                           "job-matching-model-research"):
                if needle in text:
                    forbidden.append(f"{py.name}: 含 {needle!r}")
        self.assertEqual([], forbidden,
                         f"研究脚本必须通过 _paths 解析根目录，不得硬编码: {forbidden}")

    def test_wrong_jm_root_override_is_rejected(self):
        """JM_ROOT 指向别的工程时必须显式抛错，不得静默继续。"""
        import _paths
        with self.assertRaises(_paths.RootResolutionError):
            _paths.assert_repo_root(ROOT / "reports")  # 不是仓库根
        with self.assertRaises(_paths.RootResolutionError):
            _paths.assert_repo_root(ROOT / "data" / "does-not-exist")

    def test_jm_root_override_to_real_repo_works(self):
        import _paths
        self.assertEqual(ROOT.resolve(), _paths.assert_repo_root(ROOT).resolve())

    # ---------------- D2：行尾与冻结完整性
    def test_frozen_data_files_have_no_crlf(self):
        """冻结数据文件工作区必须是 LF，否则逐字节哈希不可复现。

        范围：`git ls-files` 追踪到的标注/冻结数据（未追踪的本地产物不在
        字节完整性门禁范围内，不混入断言造成假失败）。
        """
        tracked = subprocess.run(["git", "ls-files", "--", "data/independent_eval"],
                                 capture_output=True, text=True,
                                 cwd=str(ROOT), check=True).stdout.splitlines()
        offenders = []
        for rel in tracked:
            p = ROOT / rel
            if not p.is_file() or p.suffix not in (".json", ".jsonl", ".csv"):
                continue
            if b"\r\n" in p.read_bytes():
                offenders.append(rel.replace("\\", "/"))
        self.assertGreaterEqual(len(tracked), 5, "应实际检查到多个追踪数据文件")
        self.assertEqual([], offenders,
                         f"冻结/标注数据出现 CRLF，将破坏逐字节完整性: {offenders}")

    def test_gitattributes_pins_lf_for_hashed_data(self):
        ga = ROOT / ".gitattributes"
        self.assertTrue(ga.exists(), "必须存在 .gitattributes 钉死行尾")
        text = ga.read_text(encoding="utf-8", errors="ignore")
        self.assertIn("*.jsonl text eol=lf", text)
        self.assertIn("*.json  text eol=lf", text)

    def test_frozen_pool_manifest_hash_matches_git_blob(self):
        """冻结记录的哈希必须与 Git blob 一致（权威字节），而不是工作区渲染。"""
        manifest = FROZEN_DIR / "pool_v1" / "manifest.json"
        self.assertTrue(manifest.exists())
        rec = json.loads(manifest.read_text(encoding="utf-8"))
        checked = 0
        for key, meta in rec.get("files", {}).items():
            rel = meta["path"].replace("\\", "/")
            blob = subprocess.run(
                ["git", "cat-file", "blob", f"HEAD:{rel}"],
                capture_output=True, cwd=str(ROOT),
            ).stdout
            if not blob:
                continue
            import hashlib
            self.assertEqual(meta["sha256"], hashlib.sha256(blob).hexdigest(),
                             f"{rel} 的 blob 哈希与冻结记录不一致（数据被改动）")
            self.assertEqual(meta["bytes"], len(blob), f"{rel} 字节数与冻结记录不一致")
            checked += 1
        self.assertGreaterEqual(checked, 3, "应至少复验 3 个冻结文件")

    def test_frozen_pool_verify_freeze_ok(self):
        from job_matching.annotation.freeze import verify_freeze
        manifest = FROZEN_DIR / "pool_v1" / "manifest.json"
        res = verify_freeze(manifest)
        self.assertTrue(res["ok"], f"冻结产物复验失败: {res.get('files')}")

    def test_gold_still_blocked_not_faked(self):
        """H2 真实人工 Gold 仍未冻结：evalset_* 只能有阻断记录。"""
        found = 0
        for d in sorted(FROZEN_DIR.iterdir()):
            if not d.is_dir() or not d.name.startswith("evalset"):
                continue
            found += 1
            self.assertFalse((d / "manifest.json").exists(),
                             f"{d.name} 不得出现成功冻结的 manifest（H2 仍 BLOCKED）")
            blocked = json.loads((d / "freeze_blocked.json").read_text(encoding="utf-8"))
            self.assertEqual("blocked", blocked.get("status"))
        self.assertGreaterEqual(found, 1)


if __name__ == "__main__":
    unittest.main()
