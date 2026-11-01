# -*- coding: utf-8 -*-
"""OAuth 统一数据对象（平台差异到此为止，业务层只认这两个类型）。

OAuthIdentity 的身份语义（M2 纪律，写死在文档与测试里）：
  * `subject` 是第三方平台**经服务端核验**的稳定用户标识：
      - 微信：授权返回的 OpenID（openid）
      - QQ：  QQ 互联 OpenID（oauth2.0/me 返回）
      - 微博：授权返回的 UID（uid）
  * `client_id` 参与身份命名空间：不同 AppID 下的 OpenID 语义不同，不得碰撞；
  * 昵称/头像只做展示，**永不**参与身份识别；
  * `email` 只有在平台明确声明已验证时才置 `email_verified=True`，
    未验证邮箱不得作为已验证邮箱，也不得用于自动绑定既有账号；
  * 微信 UnionID 只在真实可用时填入（与开放平台绑定关系有关），可空；
  * 不假设 QQ / 微博 / 微信之间用户 ID 具有相同语义。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class OAuthTokenResponse:
    """code 换 token 的统一结果（Provider Access Token，绝不进入浏览器/URL/日志）。"""

    provider: str
    client_id: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    # 平台特有的已核验用户标识（微信 openid / QQ openid / 微博 uid），
    # 由适配器解析；get_identity 可能再次请求资料接口。
    raw_subject: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    def describe(self) -> dict:
        """安全投影：**不含** access_token / refresh_token（日志/响应只允许用这个）。"""
        return {"provider": self.provider, "client_id": self.client_id,
                "token_type": self.token_type, "expires_in": self.expires_in,
                "scope": self.scope, "has_refresh_token": bool(self.refresh_token)}


@dataclass(frozen=True)
class OAuthIdentity:
    """统一第三方身份（唯一可信身份来源：provider + client_id + subject）。"""

    provider: str
    client_id: str
    subject: str

    union_id: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    email_verified: bool = False
    # 资料是否成功读取（平台资料接口失败时 False：身份仍有效，昵称/头像缺失不算错误）
    profile_fetched: bool = False
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.provider or not self.client_id or not self.subject:
            raise ValueError("OAuthIdentity 必须同时具备 provider / client_id / subject")

    @property
    def namespace_key(self) -> tuple[str, str, str]:
        return (self.provider, self.client_id, self.subject)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("extra", None)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "OAuthIdentity":
        return cls(
            provider=str(data.get("provider") or ""),
            client_id=str(data.get("client_id") or ""),
            subject=str(data.get("subject") or ""),
            union_id=data.get("union_id"),
            display_name=data.get("display_name"),
            avatar_url=data.get("avatar_url"),
            email=data.get("email"),
            email_verified=bool(data.get("email_verified", False)),
            profile_fetched=bool(data.get("profile_fetched", False)),
            extra=dict(data.get("extra") or {}),
        )
