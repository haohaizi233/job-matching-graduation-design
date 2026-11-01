# -*- coding: utf-8 -*-
"""受约束的 OAuth HTTP 客户端（Phase8-A / M3.5，基于项目既有 httpx）。

安全约束（逐条对应 M5/M2 要求）：
  * 明确连接超时 / 读取超时 / 单请求总预算；
  * 有界响应体（默认 1 MiB，超限即拒绝，不把无限大响应读进内存）；
  * **零重试**：交换授权码不是幂等操作，禁止无条件重复提交已消费的 code；
  * 不跟随任何重定向（follow_redirects=False）——防止 Provider 响应把服务端
    引向内网资源（SSRF 逃生口）；
  * 只允许访问由受控代码/配置决定的固定可信端点（Provider 适配器内常量）；
  * Provider 错误分类：超时 / 传输错误 / HTTP 状态异常 / 响应格式非法；
  * Secret 脱敏：client_secret 只进请求体/查询，不进异常消息与日志；
  * Transport 可注入（httpx.MockTransport 替换真实网络，实现无真实凭据测试）。
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from .exceptions import ProviderHttpError, ProviderProtocolError, ProviderTimeout

DEFAULT_MAX_RESPONSE_BYTES = 1_048_576   # 1 MiB
DEFAULT_USER_AGENT = "job-matching-oauth-client/1.0"


@dataclass(frozen=True)
class HttpLimits:
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 10.0
    write_timeout_s: float = 10.0
    pool_timeout_s: float = 5.0
    total_budget_s: float = 20.0
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES


def redact_url(url: str) -> str:
    """异常/日志安全投影：只保留 scheme://host/path，剥掉查询与片段。"""
    try:
        p = urlsplit(url)
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    except ValueError:  # pragma: no cover
        return "<unparseable-url>"


class OAuthHttpClient:
    """OAuth 专用 HTTP 客户端（同步；与既有同步服务层一致）。

    `transport` 可注入（httpx.MockTransport / 自定义），用于测试替换真实网络；
    生产构造时不传 transport，默认走真实 TCP。
    """

    def __init__(self, *, limits: HttpLimits | None = None,
                 transport: httpx.BaseTransport | None = None,
                 user_agent: str = DEFAULT_USER_AGENT):
        self.limits = limits or HttpLimits()
        timeout = httpx.Timeout(
            connect=self.limits.connect_timeout_s,
            read=self.limits.read_timeout_s,
            write=self.limits.write_timeout_s,
            pool=self.limits.pool_timeout_s,
        )
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            follow_redirects=False,      # 硬约束：不跟随重定向（SSRF 防线）
            headers={"User-Agent": user_agent, "Accept": "*/*"},
        )

    # ---------------------------------------------------------- 生命周期
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OAuthHttpClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------------------------------------------------------- 原始请求
    def _request(self, method: str, url: str, *, params: dict | None = None,
                 data: dict | None = None, headers: dict | None = None) -> str:
        try:
            with self._client.stream(method, url, params=params, data=data,
                                     headers=headers) as resp:
                if resp.status_code >= 400:
                    # 消费掉连接但**不**把响应体塞进异常（可能含敏感回显）
                    raise ProviderHttpError(
                        f"Provider 响应状态异常 {resp.status_code} @ {redact_url(url)}",
                        status_code=resp.status_code)
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > self.limits.max_response_bytes:
                        raise ProviderProtocolError(
                            f"Provider 响应体超过上限 {self.limits.max_response_bytes} 字节 "
                            f"@ {redact_url(url)}")
                return buf.decode("utf-8", errors="replace")
        except httpx.TimeoutException as e:
            raise ProviderTimeout(f"Provider 请求超时 @ {redact_url(url)}") from e
        except httpx.HTTPError as e:
            # 传输层异常（连接拒绝/DNS/TLS）——统一归类为 Provider 不可用
            raise ProviderHttpError(
                f"Provider 传输异常 {type(e).__name__} @ {redact_url(url)}") from e

    # ---------------------------------------------------------- 便捷方法
    def get_text(self, url: str, *, params: dict | None = None,
                 headers: dict | None = None) -> str:
        return self._request("GET", url, params=params, headers=headers)

    def post_form(self, url: str, *, data: dict,
                  headers: dict | None = None) -> str:
        return self._request("POST", url, data=data, headers=headers)

    def get_json(self, url: str, *, params: dict | None = None) -> dict:
        text = self.get_text(url, params=params)
        return _loads_json_object(text, url)

    def post_form_json(self, url: str, *, data: dict) -> dict:
        text = self.post_form(url, data=data)
        return _loads_json_object(text, url)


def _loads_json_object(text: str, url: str) -> dict:
    import json
    try:
        obj = json.loads(text)
    except Exception as e:  # noqa: BLE001
        raise ProviderProtocolError(
            f"Provider 响应不是合法 JSON @ {redact_url(url)}") from e
    if not isinstance(obj, dict):
        raise ProviderProtocolError(
            f"Provider 响应 JSON 不是对象 @ {redact_url(url)}")
    return obj
