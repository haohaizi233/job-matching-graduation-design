# -*- coding: utf-8 -*-
"""运行身份（Run Identity）：让每一份诊断/校验报告都能追溯到"这一次"的真实执行。

动机（Phase5-2 / Batch 0 可信 CI）：
  此前 CI 用 `diagnose_model_compat.py || true` 后只检查报告文件是否存在，
  于是仓库里**任何一份旧报告**都能冒充本次运行成功。根治办法是给每次运行
  生成不可复用的身份标识，并在消费报告时校验身份。

运行身份字段（固定，不得省略）：
  run_id            本次运行唯一 ID（时间戳 + 随机短哈希）
  git_commit        运行时工作区 HEAD（拿不到时显式 UNKNOWN，不得留空）
  git_dirty         工作区是否有未提交改动
  execution_time    运行开始时间（UTC，ISO-8601）
  python_version    解释器版本
  dependency_versions  关键三方库版本（缺失如实记 NOT_INSTALLED）
  artifact_count    本次实际扫描到的产物数量
  status            PASS / FAIL / BLOCKED / NOT_RUN / ENV_INCOMPATIBLE

能力边界：
  运行身份只能证明"报告来自哪次执行"，不能证明结论正确；
  结论正确性仍由各检查项自身的证据支撑。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from pathlib import Path

# 状态口径统一在此登记，任何脚本不得自造同义词
STATUSES = ("PASS", "FAIL", "BLOCKED", "NOT_RUN", "ENV_INCOMPATIBLE")
# 只有 PASS 才算通过；NOT_RUN / BLOCKED / ENV_INCOMPATIBLE 一律不得计入 PASS
PASSING_STATUSES = ("PASS",)

DEPENDENCY_PROBES = ("numpy", "pandas", "sklearn", "joblib", "torch", "fastapi",
                     "pydantic", "sqlalchemy", "alembic", "argon2", "yaml",
                     "httpx", "fitz", "docx")


def git_head(repo_root: Path) -> tuple[str, bool]:
    """返回 (commit_sha, is_dirty)。git 不可用时返回 ("UNKNOWN", False)。"""
    def _run(args: list[str]) -> str:
        try:
            r = subprocess.run(args, cwd=str(repo_root), capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=15)
        except Exception:
            return ""
        return (r.stdout or "").strip() if r.returncode == 0 else ""

    commit = _run(["git", "rev-parse", "HEAD"]) or "UNKNOWN"
    status = _run(["git", "status", "--porcelain"])
    return commit, bool(status)


def dependency_versions(names: tuple[str, ...] = DEPENDENCY_PROBES) -> dict[str, str]:
    """关键依赖版本。缺失/异常必须如实记录，不得静默写成 'ok'。"""
    out: dict[str, str] = {}
    for name in names:
        try:
            mod = __import__(name)
            out[name] = str(getattr(mod, "__version__", "unknown"))
        except Exception as e:  # noqa: BLE001 - 必须如实登记
            out[name] = f"NOT_INSTALLED({type(e).__name__})"
    return out


def build_run_identity(repo_root: Path, *, artifact_count: int = 0,
                       status: str = "NOT_RUN", extra: dict | None = None) -> dict:
    """构造本次运行身份。status 必须是 STATUSES 之一。"""
    if status not in STATUSES:
        raise ValueError(f"非法运行状态: {status!r}，合法值: {STATUSES}")
    commit, dirty = git_head(repo_root)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = f"run-{stamp}-{uuid.uuid4().hex[:8]}"
    identity = {
        "run_id": run_id,
        "git_commit": commit,
        "git_dirty": dirty,
        "execution_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "dependency_versions": dependency_versions(),
        "artifact_count": int(artifact_count),
        "status": status,
    }
    if extra:
        identity["extra"] = dict(extra)
    return identity


def write_run_identity(identity: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def read_run_identity(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 新鲜度校验
class StaleReportError(RuntimeError):
    """报告不是本次运行产生的，拒绝采信。"""


def assert_report_fresh(report: dict, *, expect_run_id: str | None = None,
                        expect_commit: str | None = None,
                        max_age_seconds: int | None = None,
                        source: str = "report") -> dict:
    """校验报告携带的运行身份确实是"这一次"。

    规则（任一不满足即抛 StaleReportError）：
      1. 必须存在 run_identity 块；
      2. run_id 必须等于调用方指定的 expect_run_id（通常来自 JM_RUN_ID 环境变量）；
      3. git_commit 必须等于 expect_commit（通常为当前 HEAD）；
      4. 执行时间不得早于 max_age_seconds 之前；
      5. 状态必须是登记过的合法状态。
    """
    ident = report.get("run_identity")
    if not isinstance(ident, dict):
        raise StaleReportError(f"{source} 缺少 run_identity 块，无法确认来源，拒绝采信")
    rid = ident.get("run_id")
    if not rid:
        raise StaleReportError(f"{source} 的 run_id 为空，拒绝采信")
    if expect_run_id is not None and rid != expect_run_id:
        raise StaleReportError(
            f"{source} 不是本次运行产物：run_id={rid} != 期望 {expect_run_id}，拒绝采信旧报告")
    if expect_commit is not None:
        got = ident.get("git_commit")
        if got != expect_commit:
            raise StaleReportError(
                f"{source} 的 git_commit={got} 与当前 HEAD={expect_commit} 不一致，拒绝采信旧报告")
    if max_age_seconds is not None:
        try:
            ts = time.mktime(time.strptime(ident["execution_time"], "%Y-%m-%dT%H:%M:%SZ")) - \
                time.timezone
        except Exception as e:  # noqa: BLE001
            raise StaleReportError(f"{source} 的 execution_time 不可解析: {e}") from e
        if time.time() - ts > max_age_seconds:
            raise StaleReportError(
                f"{source} 产生于 {ident['execution_time']}，已超过 {max_age_seconds}s 时效，拒绝采信")
    status = ident.get("status")
    if status not in STATUSES:
        raise StaleReportError(f"{source} 状态非法: {status!r}，拒绝采信")
    return ident


def current_run_id_from_env(default: str | None = None) -> str:
    """CI 在同一次 job 内共享的 run_id，来自 JM_RUN_ID。"""
    v = os.environ.get("JM_RUN_ID", "").strip()
    if v:
        return v
    if default is not None:
        return default
    raise RuntimeError("环境变量 JM_RUN_ID 未设置：无法建立运行身份，拒绝读取任何既有报告")


def content_fingerprint(path: Path) -> str:
    """文件内容指纹，用于证明"本次真的读到了这份产物"。"""
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
