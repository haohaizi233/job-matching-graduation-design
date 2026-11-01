# -*- coding: utf-8 -*-
"""E2E 用「模拟第三方授权服务器」（仅测试，绝不进入生产构建）。

职责：在浏览器可访问的本地 HTTP 端点上扮演外部 OAuth 平台（微信/QQ/微博），
让真实 Vue + 真实 FastAPI 的浏览器端到端链路可以**完整跑通**：

  浏览器点击「微信登录」
    -> 本站后端 POST /oauth/start 返回 authorization_url（指向本服务 /authorize）
    -> 浏览器跳到本服务授权页（真实页面，真实点击「同意授权 / 拒绝授权」）
    -> 本服务 302 回本站后端 /api/v1/auth/oauth/{provider}/callback?code&state
    -> 本站后端用 code 到本服务 /oauth/token 换 token（真实 HTTP）
    -> 本站后端到本服务 /oauth/userinfo 取身份（真实 HTTP）
    -> 本站后端签发一次性票据并 302 到前端 /#/oauth/complete
    -> 前端票据交换 -> 本站会话

纪律：
  * 本服务只模拟**外部平台**，本站业务链路（事务/票据/账号/会话）全部真实；
  * 只监听 127.0.0.1；redirect_uri 必须落在允许前缀内（默认本站 E2E 后端回调）；
  * 测试可通过 /control/* 注入身份与异常行为（code 过期 / 429 / 500 / 响应异常 /
    身份缺失 / 资料读取失败），/control/reset 复位；
  * code 一次性消费（重放返回错误），与真实平台语义一致。

用法（playwright.config.ts 的 webServer 自动拉起）：
  py -3.13 tests/e2e/fake_oauth_server.py
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

HOST = "127.0.0.1"
PORT = int(os.environ.get("JM_E2E_FAKE_OAUTH_PORT") or 8125)
# 只允许把授权码回投到本站 E2E 后端的 OAuth 回调路径（防开放重定向被测对象混淆）
ALLOW_PREFIX = (os.environ.get("JM_E2E_FAKE_REDIRECT_ALLOW")
                or "http://127.0.0.1:8123/api/v1/auth/oauth/")

BEHAVIORS = ("ok", "code_expired", "token_unavailable", "http_429", "http_500",
             "malformed", "identity_missing", "profile_fail")

_LOCK = threading.Lock()
_STATE = {
    "behavior": "ok",
    "identity": {
        "subject": "fake-subject-1",
        "display_name": "合成昵称",
        "avatar_url": "https://img.fake.test/a.png",
        "union_id": None,
        "email": None,
        "email_verified": False,
    },
    "codes": {},        # code -> {"client_id", "redirect_uri", "state", "consumed"}
    "issued": 0,
    "events": [],
}


def _log(event: str, **kw) -> None:
    with _LOCK:
        _STATE["events"].append({"event": event, **kw})
        del _STATE["events"][:-200]


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler: BaseHTTPRequestHandler, status: int, html: str) -> None:
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    handler.send_response(302)
    handler.send_header("Location", location)
    handler.send_header("Content-Length", "0")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(min(length, 65536))
    try:
        obj = json.loads(raw.decode("utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _redirect_uri_ok(redirect_uri: str) -> bool:
    try:
        p = urlsplit(redirect_uri or "")
    except ValueError:
        return False
    if p.scheme in ("", "javascript", "data") or not p.netloc:
        return False
    return urlunsplit((p.scheme, p.netloc, p.path, "", "")).startswith(ALLOW_PREFIX)


class FakeOAuthHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------- 基础
    def log_message(self, fmt, *args):  # noqa: A003 - 静默访问日志
        pass

    def do_GET(self):  # noqa: N802
        parts = urlsplit(self.path)
        path = parts.path
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        if path == "/health":
            return _json_response(self, 200, {"ok": True, "service": "fake-oauth"})
        if path == "/authorize":
            return self._authorize(query)
        if path == "/decide":
            return self._decide(query)
        if path == "/oauth/userinfo":
            return self._userinfo(query)
        if path == "/control/state":
            with _LOCK:
                return _json_response(self, 200, {
                    "behavior": _STATE["behavior"],
                    "identity": _STATE["identity"],
                    "issued_codes": _STATE["issued"],
                    "events": _STATE["events"][-20:],
                })
        return _json_response(self, 404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        parts = urlsplit(self.path)
        path = parts.path
        if path == "/oauth/token":
            return self._token(_read_form(self))
        if path == "/control/behavior":
            return self._control_behavior(_read_json_body(self))
        if path == "/control/identity":
            return self._control_identity(_read_json_body(self))
        if path == "/control/reset":
            return self._control_reset()
        return _json_response(self, 404, {"error": "not_found"})

    # ---------------------------------------------------------- 授权页
    def _authorize(self, query: dict) -> None:
        redirect_uri = query.get("redirect_uri") or ""
        state = query.get("state") or ""
        client_id = query.get("client_id") or ""
        provider = query.get("provider") or "fake"
        if not _redirect_uri_ok(redirect_uri):
            _log("authorize_reject", reason="redirect_uri")
            return _json_response(self, 400, {"error": "invalid_redirect_uri"})
        if not state:
            _log("authorize_reject", reason="state")
            return _json_response(self, 400, {"error": "missing_state"})
        hidden = {
            "redirect_uri": redirect_uri, "state": state,
            "client_id": client_id, "provider": provider,
        }
        hidden_html = "".join(
            f'<input type="hidden" name="{k}" value="{_esc(v)}">' for k, v in hidden.items())
        _log("authorize", provider=provider)
        html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>模拟第三方平台授权</title>
<style>
 body {{ font-family: system-ui, sans-serif; background:#f2f5fa; display:grid;
        place-items:center; min-height:100vh; margin:0; }}
 .card {{ background:#fff; border-radius:14px; padding:38px 34px; width:min(460px,92vw);
          box-shadow:0 12px 34px rgba(20,50,120,.14); text-align:center; }}
 h1 {{ font-size:21px; margin:0 0 12px; color:#12234a; }}
 p {{ color:#6c7a94; line-height:1.7; margin:8px 0; }}
 .row {{ display:flex; gap:14px; justify-content:center; margin-top:26px; }}
 button {{ border:0; border-radius:9px; padding:12px 26px; font-size:15px; font-weight:700;
           cursor:pointer; }}
 .allow {{ background:#2f78ff; color:#fff; }}
 .deny {{ background:#eef2fb; color:#45577c; }}
 .meta {{ font-size:12px; color:#9aa6ba; margin-top:18px; }}
</style></head>
<body>
  <div class="card">
    <h1 data-testid="fake-oauth-title">模拟「{_esc(provider)}」平台授权确认</h1>
    <p>这是 E2E 测试专用的模拟授权服务器，不是真实微信 / QQ / 微博平台。</p>
    <p>应用标识：<code>{_esc(client_id)}</code></p>
    <form method="GET" action="/decide">{hidden_html}
      <input type="hidden" name="decision" value="allow">
      <div class="row"><button class="allow" type="submit" data-testid="fake-allow">同意授权</button></div>
    </form>
    <form method="GET" action="/decide">{hidden_html}
      <input type="hidden" name="decision" value="deny">
      <div class="row"><button class="deny" type="submit" data-testid="fake-deny">拒绝授权</button></div>
    </form>
    <p class="meta">redirect_uri：{_esc(redirect_uri)}</p>
  </div>
</body></html>"""
        return _html_response(self, 200, html)

    def _decide(self, query: dict) -> None:
        redirect_uri = query.get("redirect_uri") or ""
        state = query.get("state") or ""
        decision = query.get("decision") or ""
        provider = query.get("provider") or "fake"
        if not _redirect_uri_ok(redirect_uri):
            _log("decide_reject", reason="redirect_uri")
            return _json_response(self, 400, {"error": "invalid_redirect_uri"})
        if decision != "allow":
            _log("decide_deny", provider=provider)
            qs = urlencode({"error": "access_denied",
                            "error_description": "user denied the authorization",
                            "state": state})
            return _redirect(self, f"{redirect_uri}?{qs}")
        code = f"fakecode-{secrets.token_urlsafe(12)}"
        with _LOCK:
            _STATE["codes"][code] = {
                "client_id": query.get("client_id") or "",
                "redirect_uri": redirect_uri, "state": state,
                "provider": provider, "consumed": False,
            }
            _STATE["issued"] += 1
        _log("decide_allow", provider=provider)
        qs = urlencode({"code": code, "state": state})
        return _redirect(self, f"{redirect_uri}?{qs}")

    # ---------------------------------------------------------- token
    def _token(self, form: dict) -> None:
        code = form.get("code") or ""
        redirect_uri = form.get("redirect_uri") or ""
        with _LOCK:
            behavior = _STATE["behavior"]
        _log("token_request", behavior=behavior)
        if behavior == "http_429":
            return _json_response(self, 429, {"error": "rate_limited"})
        if behavior == "http_500":
            return _json_response(self, 500, {"error": "server_error"})
        if behavior == "malformed":
            return _raw_response(self, 200, "<html>not json</html>")
        if behavior in ("code_expired", "token_unavailable"):
            return _json_response(self, 200, {"error": "invalid_grant",
                                              "error_description": behavior})
        with _LOCK:
            rec = _STATE["codes"].get(code)
            if rec is None or rec["consumed"]:
                _log("token_reject", reason="code_invalid_or_used")
                return _json_response(self, 200, {
                    "error": "invalid_grant",
                    "error_description": "code invalid or already used"})
            if redirect_uri and redirect_uri != rec["redirect_uri"]:
                _log("token_reject", reason="redirect_uri_mismatch")
                return _json_response(self, 200, {"error": "invalid_grant",
                                                  "error_description": "redirect_uri mismatch"})
            rec["consumed"] = True
            subject = "" if behavior == "identity_missing" else str(
                _STATE["identity"].get("subject") or "")
        access_token = f"fakeat-{secrets.token_urlsafe(10)}"
        _log("token_issued")
        # 真实平台语义：微信 openid / 微博 uid 在 code 换 token 时即已核验返回，
        # 资料接口只是展示信息（可失败）。
        return _json_response(self, 200, {"access_token": access_token,
                                          "expires_in": 7200, "token_type": "bearer",
                                          "subject": subject})

    # ---------------------------------------------------------- userinfo
    def _userinfo(self, query: dict) -> None:
        with _LOCK:
            behavior = _STATE["behavior"]
            identity = dict(_STATE["identity"])
        _log("userinfo_request", behavior=behavior)
        if not (query.get("access_token") or "").startswith("fakeat-"):
            return _json_response(self, 200, {"error": "invalid_access_token"})
        if behavior == "http_429":
            return _json_response(self, 429, {"error": "rate_limited"})
        if behavior == "http_500":
            return _json_response(self, 500, {"error": "server_error"})
        if behavior == "malformed":
            return _raw_response(self, 200, "<html>not json</html>")
        if behavior == "identity_missing":
            return _json_response(self, 200, {"error": "no_subject"})
        if behavior == "profile_fail":
            # 已核验 subject 可得（token 侧），资料接口失败：
            return _json_response(self, 500, {"error": "profile_unavailable"})
        return _json_response(self, 200, {
            "subject": identity.get("subject"),
            "display_name": identity.get("display_name"),
            "avatar_url": identity.get("avatar_url"),
            "union_id": identity.get("union_id"),
            "email": identity.get("email"),
            "email_verified": identity.get("email_verified"),
        })

    # ---------------------------------------------------------- 控制面
    def _control_behavior(self, body: dict) -> None:
        behavior = str(body.get("behavior") or "ok")
        if behavior not in BEHAVIORS:
            return _json_response(self, 400, {"error": "unknown_behavior",
                                              "allowed": list(BEHAVIORS)})
        with _LOCK:
            _STATE["behavior"] = behavior
        _log("control_behavior", behavior=behavior)
        return _json_response(self, 200, {"ok": True, "behavior": behavior})

    def _control_identity(self, body: dict) -> None:
        with _LOCK:
            ident = _STATE["identity"]
            for key in ("subject", "display_name", "avatar_url", "union_id",
                        "email", "email_verified"):
                if key in body:
                    ident[key] = body[key]
            snapshot = dict(ident)
        _log("control_identity", subject=snapshot.get("subject"))
        return _json_response(self, 200, {"ok": True, "identity": snapshot})

    def _control_reset(self) -> None:
        with _LOCK:
            _STATE["behavior"] = "ok"
            _STATE["codes"].clear()
            _STATE["issued"] = 0
            _STATE["identity"] = {
                "subject": "fake-subject-1", "display_name": "合成昵称",
                "avatar_url": "https://img.fake.test/a.png", "union_id": None,
                "email": None, "email_verified": False,
            }
            _STATE["events"].clear()
        _log("control_reset")
        return _json_response(self, 200, {"ok": True})


def _raw_response(handler: BaseHTTPRequestHandler, status: int, text: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_form(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(min(length, 65536)) if length > 0 else b""
    try:
        return dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
    except Exception:  # noqa: BLE001
        return {}


def _esc(value) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    server = ThreadingHTTPServer((HOST, PORT), FakeOAuthHandler)
    print(f"[fake-oauth] listening http://{HOST}:{PORT} (allow={ALLOW_PREFIX})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
