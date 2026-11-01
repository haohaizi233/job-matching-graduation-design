import { apiRequest } from './http'
import type { AuthUser, LoginResult } from './types'

/** 第三方 OAuth 平台（后端白名单固定为这三家） */
export type OAuthProvider = 'wechat' | 'qq' | 'weibo'

/** 授权模式：登录 / 绑定当前账号 */
export type OAuthMode = 'login' | 'bind'

/** 平台状态：disabled / configured_pending_verification / available */
export type OAuthProviderState = 'disabled' | 'configured_pending_verification' | 'available'

export interface OAuthProviderStatus {
  id: OAuthProvider
  label: string
  enabled: boolean
  status: OAuthProviderState
  reason_code?: string | null
}

export interface OAuthStartResult {
  authorization_url: string
  expires_in: number
  /** 事务短标识（Cookie 名后缀；非安全凭据） */
  rid: string
  mode: OAuthMode
  return_path: string
}

export interface OAuthBoundIdentity {
  id: string
  provider: OAuthProvider
  display_name: string | null
  avatar_url: string | null
  created_at: string
  last_login_at: string | null
}

export interface OAuthIdentityList {
  items: OAuthBoundIdentity[]
  password_login_available: boolean
}

/** GET /auth/oauth/providers */
export async function fetchProviders(): Promise<OAuthProviderStatus[]> {
  const data = await apiRequest<{ providers: OAuthProviderStatus[] }>('/auth/oauth/providers', {
    auth: false,
  })
  return data.providers
}

/** POST /auth/oauth/start（bind 模式自动携带本站 Bearer） */
export async function startOAuth(input: {
  provider: OAuthProvider
  mode?: OAuthMode
  return_path?: string
}): Promise<OAuthStartResult> {
  return apiRequest<OAuthStartResult>('/auth/oauth/start', {
    method: 'POST',
    json: {
      provider: input.provider,
      mode: input.mode ?? 'login',
      return_path: input.return_path ?? null,
    },
    auth: true,
  })
}

/**
 * POST /auth/oauth/exchange：一次性票据（HttpOnly Cookie）交换本站会话。
 * login 模式返回与 /auth/login 一致的 LoginResult；bind 模式返回绑定结果。
 */
export async function exchangeOAuthTicket(rid: string): Promise<
  | { mode: 'login'; result: LoginResult }
  | { mode: 'bind'; bound: boolean; identity: OAuthBoundIdentity; already_bound: boolean }
> {
  const data = await apiRequest<Record<string, unknown>>('/auth/oauth/exchange', {
    method: 'POST',
    json: { rid },
    auth: true,
  })
  if (data && typeof data.token === 'string') {
    return { mode: 'login', result: data as unknown as LoginResult }
  }
  return {
    mode: 'bind',
    bound: Boolean(data.bound),
    identity: data.identity as OAuthBoundIdentity,
    already_bound: Boolean(data.already_bound),
  }
}

/** GET /auth/oauth/identities */
export async function listBoundIdentities(): Promise<OAuthIdentityList> {
  return apiRequest<OAuthIdentityList>('/auth/oauth/identities')
}

/** DELETE /auth/oauth/identities/{ref}（ref = provider 或 identity_id） */
export async function unbindIdentity(ref: string): Promise<{ unbound: boolean }> {
  return apiRequest<{ unbound: boolean }>(
    `/auth/oauth/identities/${encodeURIComponent(ref)}`,
    { method: 'DELETE' },
  )
}

/** POST /auth/oauth/set-password（纯 OAuth 账号补设本站密码） */
export async function setOAuthPassword(newPassword: string): Promise<{
  password_set: boolean
  revoked_sessions: number
}> {
  return apiRequest<{ password_set: boolean; revoked_sessions: number }>(
    '/auth/oauth/set-password',
    { method: 'POST', json: { new_password: newPassword } },
  )
}

export type { AuthUser }
