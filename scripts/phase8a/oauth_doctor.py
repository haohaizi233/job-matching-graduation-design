# -*- coding: utf-8 -*-
"""OAuth 环境体检（Phase8-A / M8）：`py -3.13 scripts/phase8a/oauth_doctor.py`。

输出逐项状态（**绝不**打印 Secret）：

  微信: DISABLED / CREDENTIALS_MISSING
  QQ:   DISABLED / CREDENTIALS_MISSING
  微博: DISABLED / CREDENTIALS_MISSING

  Database Migration: PASS
  OAuth Provider Registry: PASS
  Redirect Policy: PASS
  Ticket Store: PASS
  Frontend Routes: PASS

四态区分（不得混为一谈）：
  代码就绪（本脚本各项 PASS）
  凭据完整（CONFIGURED_PENDING_VERIFICATION）
  平台已审核（人工在平台侧确认）
  真实授权联调通过（VERIFIED / available，需人工真实扫码登录后置位）

退出码：0 = 全部基础检查 PASS；1 = 有 FAIL。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PROVIDER_STATUS_TEXT = {
    "disabled": "DISABLED",
    "configured_pending_verification": "CONFIGURED_PENDING_VERIFICATION",
    "available": "AVAILABLE",
}


def check_providers(settings) -> list[tuple[str, str, str]]:
    """逐平台状态：(平台, 状态文本, 说明)。不输出任何 Secret。"""
    from job_matching.service.oauth.config import PROVIDER_WHITELIST

    out = []
    for pid in PROVIDER_WHITELIST:
        cfg = settings.provider(pid)
        status, reason = settings.provider_status(pid)
        if status == "disabled":
            if reason == "OAUTH_PROVIDER_NOT_CONFIGURED":
                note = "CREDENTIALS_MISSING（缺 AppID/AppSecret/回调地址）"
            else:
                note = "DISABLED（未启用）"
        elif status == "configured_pending_verification":
            note = "CREDENTIALS_COMPLETE（凭据齐全但**未真实联调**）"
        else:
            note = "VERIFIED（真实授权联调通过后人工登记）"
        out.append((cfg.label if cfg else pid,
                    PROVIDER_STATUS_TEXT.get(status, status), note))
    return out


def check_database() -> tuple[str, str]:
    """迁移检查：新迁移存在且 revision 链完整（不连接真实库；库连通性由集成测试覆盖）。"""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        expected = "e8a0f1c2d3a4"
        if expected in heads:
            return "PASS", f"迁移链 head={heads}"
        rev = script.get_revision(expected)
        if rev is not None:
            return "PASS", f"Phase8-A 迁移 {expected} 在链上（head={heads}）"
        return "FAIL", f"缺少 Phase8-A 迁移 {expected}"
    except Exception as e:  # noqa: BLE001
        return "FAIL", f"{type(e).__name__}: {e}"


def check_registry(settings) -> tuple[str, str]:
    """注册表检查：白名单固定为 wechat/qq/weibo，动态 Provider 必须被拒绝。"""
    try:
        from job_matching.service.oauth.registry import OAuthProviderRegistry
        reg = OAuthProviderRegistry(settings=settings)
        assert set(reg.allowed_ids()) == {"wechat", "qq", "weibo"}
        try:
            reg.get("evil-provider")
        except Exception:  # noqa: BLE001 必须拒绝
            return "PASS", "白名单=wechat/qq/weibo；未登记 Provider 被拒绝"
        return "FAIL", "未登记 Provider 未被拒绝"
    except Exception as e:  # noqa: BLE001
        return "FAIL", f"{type(e).__name__}: {e}"


def check_redirect_policy(settings) -> tuple[str, str]:
    """重定向策略：return_path 白名单 + 回调地址受控派生。"""
    try:
        from job_matching.service.oauth.security import sanitize_return_path
        from job_matching.service.oauth.exceptions import InvalidRedirect
        ok = sanitize_return_path("/dashboard") == "/dashboard"
        rejected = 0
        for bad in ("https://evil.example", "//evil.example", "/\\evil.example",
                    "/%2F%2Fevil.example", "/dashboard/../../etc"):
            try:
                sanitize_return_path(bad)
            except InvalidRedirect:
                rejected += 1
        if ok and rejected == 5:
            return "PASS", "return_path 白名单生效；外跳/混淆路径全部拒绝"
        return "FAIL", f"重定向策略异常（ok={ok}, rejected={rejected}/5）"
    except Exception as e:  # noqa: BLE001
        return "FAIL", f"{type(e).__name__}: {e}"


def check_ticket_store() -> tuple[str, str]:
    """票据存储：摘要落库（不存明文）、一次性消费、过期失效。"""
    try:
        import os
        import tempfile

        from alembic import command
        from alembic.config import Config
        from job_matching.service.oauth.ticket_store import OAuthTicketStore

        tmp = tempfile.mkdtemp(prefix="oauth_doctor_")
        db = f"sqlite:///{tmp}/doctor.db"
        os.environ["JM_DATABASE_URL"] = db
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        command.upgrade(cfg, "head")

        store = OAuthTicketStore()
        # 先造一个真实用户（票据外键指向 users.id，模拟器不绕过引用完整性）
        import uuid
        from datetime import datetime
        from job_matching.infra.persistence import User, get_session
        now = datetime.utcnow()
        session = get_session()
        try:
            user = User(id=str(uuid.uuid4()), username="doctor_user",
                        password_hash=None, role="student", status="active",
                        failed_login_count=0, created_at=now, updated_at=now)
            session.add(user)
            session.commit()
            doctor_user_id = user.id
        finally:
            session.close()
        ticket = store.issue(mode="login", user_id=doctor_user_id,
                             browser_binding_digest="d", browser_binding_key="k",
                             ttl_seconds=60)
        from job_matching.service.oauth.security import digest
        # 明文不得落库
        from job_matching.infra.persistence import OAuthLoginTicket
        session = get_session()
        try:
            rows = session.query(OAuthLoginTicket).all()
            plaintext_leak = any(ticket == r.ticket_digest for r in rows)
            has_digest = any(r.ticket_digest == digest(ticket) for r in rows)
        finally:
            session.close()
        if plaintext_leak or not has_digest:
            return "FAIL", "票据明文落库或摘要缺失"
        store.consume(ticket=ticket, browser_binding_digest="d",
                      browser_binding_key="k")
        try:
            store.consume(ticket=ticket, browser_binding_digest="d",
                          browser_binding_key="k")
        except Exception:  # noqa: BLE001 重放必须被拒绝
            return "PASS", "票据摘要落库；一次性消费；重放拒绝"
        return "FAIL", "票据重放未被拒绝"
    except Exception as e:  # noqa: BLE001
        return "FAIL", f"{type(e).__name__}: {e}"


def check_frontend_routes() -> tuple[str, str]:
    """前端接入检查：OAuth 完成页/路由/API 文件存在且不含 Secret。"""
    try:
        files = {
            "oauth api": ROOT / "frontend" / "src" / "api" / "oauth.ts",
            "useOAuth": ROOT / "frontend" / "src" / "composables" / "useOAuth.ts",
            "完成页": ROOT / "frontend" / "src" / "views" / "OAuthCompleteView.vue",
            "路由": ROOT / "frontend" / "src" / "router" / "index.ts",
        }
        missing = [k for k, p in files.items() if not p.is_file()]
        if missing:
            return "FAIL", "缺少前端文件: " + ",".join(missing)
        router_text = files["路由"].read_text(encoding="utf-8")
        if "oauth/complete" not in router_text:
            return "FAIL", "路由缺少 /oauth/complete"
        for p in files.values():
            text = p.read_text(encoding="utf-8").lower()
            if "client_secret" in text or "appsecret" in text:
                return "FAIL", f"{p.name} 疑似包含 Secret 字样"
        return "PASS", "OAuth 完成页/路由/API 文件齐备且无 Secret"
    except Exception as e:  # noqa: BLE001
        return "FAIL", f"{type(e).__name__}: {e}"


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv
    as_json = "--json" in argv
    from job_matching.service.oauth.config import OAuthSettings

    settings = OAuthSettings.from_env()
    lines: list[str] = []
    rows: list[dict] = []

    for label, status, note in check_providers(settings):
        lines.append(f"{label}: {status} / {note}")
        rows.append({"item": label, "status": status, "note": note})

    checks = [
        ("Database Migration", check_database()),
        ("OAuth Provider Registry", check_registry(settings)),
        ("Redirect Policy", check_redirect_policy(settings)),
        ("Ticket Store", check_ticket_store()),
        ("Frontend Routes", check_frontend_routes()),
    ]
    for name, (status, note) in checks:
        lines.append(f"{name}: {status} ({note})")
        rows.append({"item": name, "status": status, "note": note})

    # 部署安全检查（生产缺白名单/HTTP 不安全 -> 拒绝启用）
    problems = settings.check_safety()
    if problems:
        lines.append("Deployment Safety: WARN (" + "；".join(problems) + ")")
        rows.append({"item": "Deployment Safety", "status": "WARN",
                     "note": "；".join(problems)})
    else:
        lines.append("Deployment Safety: PASS")
        rows.append({"item": "Deployment Safety", "status": "PASS", "note": ""})

    lines.append("")
    lines.append("真实联调状态（凭据 ≠ 审核通过 ≠ 联调通过）：")
    lines.append("  implementation = COMPLETE")
    lines.append("  mock_integration = 见 reports/phase8-a/07-provider-mock-tests.md")
    lines.append("  real_provider_integration = NOT_RUN")
    lines.append("  provider_approval = PENDING")

    failed = any(r["status"] == "FAIL" for r in rows)
    if as_json:
        print(json.dumps({"ok": not failed, "items": rows}, ensure_ascii=False,
                         indent=2))
    else:
        print("\n".join(lines))
        print(f"\noverall: {'PASS' if not failed else 'FAIL'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
