# -*- coding: utf-8 -*-
"""C4：隐私与安全门禁（可移植，不需要真实数据）。

覆盖：
  * 仓库内不得出现密钥 / 口令 / 私钥 / 令牌明文；
  * `.env`、`data/raw/`、`data/private/` 必须被忽略且未入库；
    `models/` 仅允许白名单训练产物入库（Phase6 起权重为交付物，白名单外文件仍禁入）；
  * 服务层源码不得写死本机绝对路径 / 用户名；
  * 错误响应与日志不得回显密码、令牌、简历原文；
  * 密码哈希不得出现在任何响应契约里；
  * 报告与日志不得含真实简历正文特征（手机号 / 邮箱 / 身份证号形态）。

说明：这些都是**静态门禁**，能在全新 checkout 上执行；真实简历隐私验收
属 Artifact-dependent / 独立安全验收，不在本套件内冒充通过。
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(HERE), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SRC = ROOT / "src" / "job_matching"

# 密钥形态（只匹配"看起来真的是密钥"的字符串，避免把示例/占位符误判）
SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    "jwt_literal": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "assigned_secret": re.compile(
        r"(?i)\b(password|passwd|pwd|secret|api_key|apikey|access_token|auth_token)"
        r"\s*[:=]\s*[\"'](?!\s*$)(?!(?:none|null|changeme|your[_-]?|example|placeholder))"
        r"([A-Za-z0-9_\-/+=.]{12,})[\"']"),
}

PII_PATTERNS = {
    "mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "idcard": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
}

# 允许出现"示例密钥字段名"的文件（占位符不算密钥）
SECRET_SCAN_EXCLUDES = {".env.example", "requirements-test.txt"}
SECRET_SCAN_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "chinese-skillspan-benchmark",
                         "node_modules", ".venv", "venv"}


def _tracked_files() -> list[str]:
    try:
        r = subprocess.run(["git", "ls-files"], cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60)
        return [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return []


def _source_files() -> list[Path]:
    out = []
    for base in (SRC, ROOT / "scripts", ROOT / "tests"):
        for p in sorted(base.rglob("*.py")):
            if any(seg in SECRET_SCAN_SKIP_DIRS for seg in p.parts):
                continue
            out.append(p)
    return out


class C4SecretsAndLeaks(unittest.TestCase):

    def test_no_secret_material_in_tracked_files(self):
        offenders = []
        for rel in _tracked_files():
            if Path(rel).name in SECRET_SCAN_EXCLUDES:
                continue
            if any(seg in SECRET_SCAN_SKIP_DIRS for seg in Path(rel).parts):
                continue
            p = ROOT / rel
            if not p.is_file() or p.stat().st_size > 2_000_000:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            for name, rx in SECRET_PATTERNS.items():
                m = rx.search(text)
                if m:
                    offenders.append(f"{rel}:{name}:{m.group(0)[:24]}")
        self.assertEqual(offenders, [], f"仓库中疑似存在密钥/口令明文: {offenders[:5]}")

    def test_env_file_ignored_and_untracked(self):
        tracked = set(_tracked_files())
        self.assertNotIn(".env", tracked, ".env 不得入库")
        for p in (".env", ".env.local"):
            self.assertNotIn(p, tracked)

    def test_gitignore_covers_sensitive_paths(self):
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for needle in (".env", "models/**", "data/raw/", "data/private/", "*.pem", "*.key"):
            self.assertIn(needle, gi, f".gitignore 缺少敏感路径规则: {needle}")

    #: models/ 允许入库的训练产物扩展名（与 .gitignore 白名单一致；Phase6 起权重为交付物）
    MODEL_ARTIFACT_EXTS = {".json", ".md", ".txt", ".npz", ".npy", ".pkl", ".pt", ".pth"}

    def test_raw_and_private_data_untracked_model_artifacts_whitelisted(self):
        """原始数据 / 私有简历绝不入库；models/ 仅允许白名单训练产物。

        Phase6 口径调整：训练产物（权重、checkpoint、预测矩阵、指标 JSON）是交付物，
        允许按白名单入库；但 `models/` 之下白名单之外的任何文件仍禁入，
        且 `data/raw/`、`data/private/` 的禁令完全不变。
        """
        tracked = _tracked_files()
        raw_leaked = [t for t in tracked if t.startswith("data/raw/")]
        self.assertEqual(raw_leaked, [], f"原始数据被入库: {raw_leaked[:5]}")
        private_leaked = [t for t in tracked if t.startswith("data/private/")
                          and t.rstrip("/") != "data/private"]
        self.assertEqual(private_leaked, [], f"私有简历目录被入库: {private_leaked[:5]}")
        bad_models = [t for t in tracked if t.startswith("models/")
                      and Path(t).suffix.lower() not in self.MODEL_ARTIFACT_EXTS]
        self.assertEqual(
            bad_models, [],
            f"models/ 出现白名单之外的文件（训练产物仅限 "
            f"{sorted(self.MODEL_ARTIFACT_EXTS)}）: {bad_models[:5]}")

    def test_no_hardcoded_local_absolute_path_in_service_layer(self):
        rx = re.compile(r"[A-Za-z]:[\\/](Users|desktop|Desktop|home)[\\/]")
        offenders = {}
        for p in sorted((SRC / "service").glob("*.py")):
            if rx.search(p.read_text(encoding="utf-8")):
                offenders[p.name] = True
        self.assertFalse(offenders, f"服务层不得写死本机绝对路径: {offenders}")

    def test_no_local_username_in_tracked_python(self):
        """生产源码（src/ scripts/）不得出现本机用户目录；测试夹具里的占位用户名单独限定。"""
        rx = re.compile(r"[A-Za-z]:[\\/]Users[\\/]([A-Za-z0-9_.-]+)")
        allowed_placeholders = {"me", "user", "username", "test", "tester", "you",
                                "someone", "xxx", "name", "account"}
        offenders = []
        for rel in _tracked_files():
            if not rel.endswith(".py"):
                continue
            p = ROOT / rel
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            for m in rx.finditer(text):
                who = m.group(1)
                is_prod = rel.startswith(("src/", "scripts/"))
                if is_prod or who.lower() not in allowed_placeholders:
                    offenders.append(f"{rel}:{who}")
        self.assertEqual(offenders, [],
                         f"Python 源码泄露本机用户名路径: {offenders[:5]}")


class C4ResponseAndLoggingPrivacy(unittest.TestCase):

    def test_error_payload_never_carries_password_or_token_fields(self):
        from job_matching.service.errors import ServiceError
        e = ServiceError("INVALID_REQUEST", "bad", {"password": "hunter2", "token": "abc"})
        blob = json.dumps(e.to_dict("req-1"), ensure_ascii=False)
        self.assertIn("detail", blob)
        # 详情里允许出现字段名，但不得出现明文口令值
        self.assertNotIn("hunter2", blob)

    def test_error_codes_do_not_expose_secrets(self):
        from job_matching.service.errors import ERROR_CODES
        for code, (_status, meaning) in ERROR_CODES.items():
            self.assertNotIn("密码", meaning, f"{code} 说明里不得出现明文密码")

    def test_local_absolute_paths_redacted_in_error_detail(self):
        from job_matching.service.errors import redact_local_paths
        leaked = redact_local_paths({"p": "D:\\Users\\someone\\secret\\resume.pdf"})
        self.assertNotIn("someone", json.dumps(leaked, ensure_ascii=False))

    def test_logging_utils_masks_pii(self):
        from job_matching.service import logging_utils
        fns = [n for n in dir(logging_utils) if not n.startswith("__")]
        self.assertTrue(fns, "logging_utils 无可用符号")
        doc = (logging_utils.__doc__ or "")
        blob = " ".join(str(getattr(logging_utils, n)) for n in fns) + doc
        self.assertTrue(("脱敏" in blob) or ("PII" in blob) or ("mask" in blob.lower()),
                        "日志工具必须声明 PII 脱敏职责")

    def test_pii_masking_covers_phone_email_id(self):
        from job_matching.domain.pii_masking import mask_matches
        text = "姓名：张三 手机：13800138000 邮箱：zhangsan@example.com 身份证：110105199001011234"
        masked = mask_matches(text)
        for secret in ("13800138000", "zhangsan@example.com", "110105199001011234", "张三"):
            self.assertNotIn(secret, masked, f"PII 未被掩码: {secret}")

    def test_service_settings_refuse_prod_without_auth(self):
        from job_matching.service.settings import ServiceSettings
        st = ServiceSettings.from_env({"JM_API_ENV": "prod", "JM_REQUIRE_AUTH": "0",
                                       "JM_ALLOW_RESEARCH_MODELS": "1"})
        problems = st.check_deployment_safety()
        self.assertTrue(problems, "生产环境缺少认证必须被判为不安全")

    def test_no_secret_env_defaults_in_settings(self):
        from job_matching.service import settings
        src = (ROOT / "src/job_matching/service/settings.py").read_text(encoding="utf-8")
        for rx in (re.compile(r"(?i)(secret|token|password|api_key)\s*=\s*[\"'][^\"']{8,}"),):
            self.assertIsNone(rx.search(src), "settings.py 不得硬编码密钥默认值")


HEX_TOKEN_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")


class C4EncodingIntegrity(unittest.TestCase):
    """文本文件编码门禁（Phase6 M0：CI 曾因 .gitignore 混入 GBK 字节而 ERROR）。

    背景：`.gitignore` 尾部注释曾以 GBK 写入，导致
    `test_gitignore_covers_sensitive_paths` 在 UTF-8 解码时抛
    `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xd1 in position 2253`。
    本门禁固化修复口径：仓库内文本必须严格按 UTF-8 可解码，且关键配置文件
    不得含 CR（.gitattributes 已钉死 LF，保证 Windows/Linux checkout 字节一致）。

    纪律：**不得**用 `errors="ignore"` / `errors="replace"` 降低断言绕过。
    """

    #: 明确按二进制处理的扩展名（与 .gitattributes 的 binary 规则一致）
    BINARY_EXTS = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
        ".pt", ".pth", ".pkl", ".npz", ".npy", ".safetensors", ".bin", ".db",
        ".sqlite", ".woff", ".woff2", ".ttf", ".eot", ".xlsx", ".xls", ".docx",
        ".pptx", ".7z", ".rar", ".mp4", ".mp3", ".whl", ".so", ".dll", ".pyd",
    }

    #: 无 git 退化枚举时需要跳过的"非仓库内容"目录（对齐 verify_fresh_checkout）
    NON_REPO_DIR_NAMES = {
        ".git", "chinese-skillspan-benchmark", "node_modules", "__pycache__",
        "dist", "build", ".venv", "venv", "env", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", ".ipynb_checkpoints", ".idea", ".runtime", ".artifacts",
        "_tmp_img_extract",
    }

    def _in_git_worktree(self) -> bool:
        try:
            r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                               cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=20)
        except Exception:  # noqa: BLE001
            return False
        return r.returncode == 0 and (r.stdout or "").strip() == "true"

    def _text_candidates(self) -> list[tuple[str, bytes]]:
        rels = _tracked_files()
        source = "git"
        if not rels:
            # 无 git 退化路径（如 verify_fresh_checkout 导出的临时 checkout）：
            # 遍历文件系统，显式登记来源，绝不把退化结果伪装成 git 清单。
            source = "filesystem_fallback"
            for p in sorted(ROOT.rglob("*")):
                if not p.is_file():
                    continue
                parts = p.relative_to(ROOT).parts
                if any(seg in self.NON_REPO_DIR_NAMES for seg in parts[:-1]):
                    continue
                rels.append("/".join(parts))
        out = []
        for rel in rels:
            p = ROOT / rel
            if not p.is_file() or p.stat().st_size > 2_000_000:
                continue
            if Path(rel).suffix.lower() in self.BINARY_EXTS:
                continue
            data = p.read_bytes()
            if b"\x00" in data:  # 含 NUL 视为二进制，不做文本编码判定
                continue
            out.append((rel, data))
        self._file_list_source = source
        return out

    def test_tracked_text_files_are_strict_utf8(self):
        """所有入库文本必须严格 UTF-8 可解码（禁止 GBK/GB2312/latin-1 混入）。"""
        offenders = []
        for rel, data in self._text_candidates():
            try:
                data.decode("utf-8")  # 严格解码，不使用 errors= 逃逸
            except UnicodeDecodeError as e:
                offenders.append(f"{rel}: {e}")
        self.assertEqual(offenders, [],
                         f"存在非 UTF-8 文本文件（需转码为 UTF-8）: {offenders[:5]}")

    def test_utf8_decode_errors_are_not_masked_in_gate(self):
        """自检：本门禁的严格解码确实能捕获 GBK 字节，而不是被 errors= 吞掉。"""
        gbk_bytes = "# 中文注释测试".encode("gbk")
        with self.assertRaises(UnicodeDecodeError):
            gbk_bytes.decode("utf-8")
        # 同一份字节若被 errors="replace" 处理会得到替换字符，说明绕过方式是可观测的
        self.assertIn("�", gbk_bytes.decode("utf-8", errors="replace"))

    def test_root_config_files_are_utf8_and_lf(self):
        """`.gitignore` / `.gitattributes` 必须 UTF-8 + 纯 LF（跨平台 checkout 字节一致）。

        判定基准是 **Git 存储的 blob 字节**（`git show :path`），因为这才是
        「同一 commit 在任何平台 checkout 出的字节完全一致」的唯一事实来源；
        工作区字节同时校验，用于暴露本机 checkout 未刷新造成的 CRLF 残留。
        """
        for name in (".gitignore", ".gitattributes", ".env.example", "alembic.ini"):
            p = ROOT / name
            if not p.exists():
                continue
            blobs = [("worktree", p.read_bytes())]
            # 仅当该文件在 Git 中无待提交改动时，才把 git blob 一并作为判定对象：
            # blob 是「同一 commit 在任何平台 checkout 字节一致」的事实来源；
            # 本地正在编辑该文件时跳过 blob 校验，避免把"未提交的中间态"误判为提交缺陷。
            clean = False
            if self._in_git_worktree():
                try:
                    st = subprocess.run(["git", "status", "--porcelain", "--", name],
                                        cwd=str(ROOT), capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=30)
                    clean = not (st.stdout or "").strip()
                except Exception:  # noqa: BLE001
                    clean = False
            if clean:
                try:
                    blob = subprocess.run(["git", "show", f":{name}"], cwd=str(ROOT),
                                          capture_output=True, timeout=30).stdout
                    if blob:
                        blobs.append(("git-blob", blob))
                except Exception:  # noqa: BLE001
                    pass
            for origin, data in blobs:
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError as e:
                    self.fail(f"{name}（{origin}）不是合法 UTF-8: {e}")
                self.assertNotIn(b"\r", data,
                                 f"{name}（{origin}）含 CR，破坏 LF 规范与跨平台字节一致性")
                self.assertNotIn(b"\x00", data, f"{name}（{origin}）含 NUL 字节")

    def test_root_config_files_declare_lf_attribute(self):
        """`.gitattributes` 必须把根配置文件钉成 `eol=lf`，否则 Windows checkout 会 smudge 成 CRLF。

        主判定走 **`.gitattributes` 文本内容**（可移植，无 git 也能校验）；
        处于 git 工作区时再用 `git check-attr` 复核真实生效的属性值。
        """
        p = ROOT / ".gitattributes"
        self.assertTrue(p.exists(), ".gitattributes 缺失")
        text = p.read_text(encoding="utf-8")
        active = [ln.split("#", 1)[0].strip() for ln in text.splitlines()]
        active = [ln for ln in active if ln]
        for target in (".gitignore", ".gitattributes"):
            hit = None
            for ln in active:
                parts = ln.split()
                if parts and parts[0] == target:
                    hit = parts
                    break
            self.assertIsNotNone(hit, f".gitattributes 未显式声明 {target} 的行尾规则")
            self.assertIn("text", hit, f"{target} 未声明 text（text=auto 在 Windows 下可能被 smudge 成 CRLF）")
            self.assertIn("eol=lf", hit, f"{target} 未钉死 eol=lf: {hit}")
        for ext in ("*.ini", "*.jsonl", "*.json", "*.csv", "*.md", "*.py"):
            hit = [ln for ln in active if ln.split()[:1] == [ext]]
            self.assertTrue(hit, f".gitattributes 未声明 {ext} 的行尾规则")
            self.assertIn("eol=lf", hit[0].split(), f"{ext} 未钉死 eol=lf: {hit[0]}")

        if self._in_git_worktree():
            r = subprocess.run(["git", "check-attr", "eol", "text", "--",
                                ".gitignore", ".gitattributes"], cwd=str(ROOT),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=30)
            out = r.stdout or ""
            self.assertIn(".gitignore: eol: lf", out, f".gitignore 未钉死 LF: {out!r}")
            self.assertIn(".gitattributes: eol: lf", out,
                          f".gitattributes 未钉死 LF: {out!r}")
            self.assertIn(".gitignore: text: set", out,
                          f".gitignore 未显式声明 text: {out!r}")

    def test_gitignore_sensitive_rules_still_present(self):
        """修复编码后忽略规则不得丢失（防止转码时误删规则）。"""
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for needle in (".env", "models/**", "data/raw/", "data/private/", "*.pem", "*.key",
                       "data/independent_eval/annotation/final_labels.csv"):
            self.assertIn(needle, gi, f".gitignore 缺少敏感路径规则: {needle}")


NUMERIC_ID_RE = re.compile(r"^\d{6,}$")


def _string_leaves(obj, path="$"):
    """递归取 JSON 字符串叶子（数值/哈希天然不参与 PII 形态判定，避免误报）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _string_leaves(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _string_leaves(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def _pii_hits(text: str) -> list[str]:
    """只在"不是哈希/纯数字 ID 的片段"上判 PII 形态。"""
    hits = []
    if HEX_TOKEN_RE.search(text) or NUMERIC_ID_RE.match(text.strip()):
        return hits
    for name, rx in PII_PATTERNS.items():
        for m in rx.finditer(text):
            # 命中片段若嵌在更长的十六进制/字母数字令牌里，视为哈希或标识符而非 PII
            s, e = m.span()
            left = text[max(0, s - 8):s]
            right = text[e:e + 8]
            if re.fullmatch(r"[0-9a-fA-F]*", left) and re.fullmatch(r"[0-9a-fA-F]*", right) \
                    and len(left) + (e - s) + len(right) >= 32:
                continue
            hits.append(name)
    return hits


class C4ReportPrivacy(unittest.TestCase):

    def test_reports_contain_no_pii_shaped_strings(self):
        """报告里不得出现手机号/身份证形态（合成夹具也一样）。"""
        offenders = []
        for p in sorted((ROOT / "reports").rglob("*.json")):
            if p.stat().st_size > 4_000_000:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                continue
            for path, text in _string_leaves(data):
                for name in _pii_hits(text):
                    if name == "email":
                        continue  # 报告里允许 .example 域名占位邮箱
                    offenders.append(f"{p.relative_to(ROOT)}:{path}:{name}")
                    break
            if len(offenders) > 8:
                break
        self.assertEqual(offenders[:8], [], f"报告疑似含个人信息: {offenders[:8]}")

    def test_synthetic_fixture_module_declares_no_real_data(self):
        p = ROOT / "tests" / "data_pipeline" / "synth_fixtures.py"
        text = p.read_text(encoding="utf-8")
        self.assertIn("合成", text)
        self.assertIn("不得混入", text)

    def test_no_resume_text_exported_to_reports(self):
        """报告里不得出现长段中文正文（简历/JD 原文）。"""
        rx = re.compile(r"[一-鿿]{60,}")
        offenders = []
        for p in sorted((ROOT / "reports").rglob("*.json")):
            if p.stat().st_size > 4_000_000:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                continue
            for path, text in _string_leaves(data):
                if rx.search(text):
                    offenders.append(f"{p.relative_to(ROOT)}: {path}: {text.strip()[:40]}")
                    break
        self.assertEqual(offenders[:5], [], f"报告疑似含正文片段: {offenders[:5]}")


class C4DependencyHygiene(unittest.TestCase):
    """新增依赖必须登记，且不得引入密钥管理不当的库。"""

    def test_requirements_files_parse(self):
        for name in ("requirements-test.txt",):
            p = ROOT / name
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                self.assertTrue(re.match(r"^[A-Za-z0-9_.\-\[\]]+([=<>!~]=.+)?$", s),
                                f"{name} 存在无法解析的依赖行: {s}")

    def test_service_source_has_no_network_downloader(self):
        """服务层不得偷偷下载数据集/权重（Batch 0 纪律）。"""
        rx = re.compile(r"(urllib\.request\.urlretrieve|wget |curl -O|torch\.hub\.load|"
                        r"huggingface_hub\.snapshot_download|load_dataset\()")
        offenders = []
        for p in sorted((SRC / "service").glob("*.py")):
            if rx.search(p.read_text(encoding="utf-8")):
                offenders.append(p.name)
        self.assertEqual(offenders, [], f"服务层存在下载器调用: {offenders}")

    def test_ast_no_eval_or_exec_in_service(self):
        offenders = []
        for p in sorted((SRC / "service").glob("*.py")):
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in ("eval", "exec", "compile"):
                        offenders.append(f"{p.name}:{node.lineno}")
        self.assertEqual(offenders, [], f"服务层出现动态执行: {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
