import { computed, ref } from 'vue'

import {
  exchangeOAuthTicket,
  fetchProviders,
  listBoundIdentities,
  setOAuthPassword,
  startOAuth,
  unbindIdentity,
} from '@/api/oauth'
import type { OAuthIdentityList, OAuthMode, OAuthProvider, OAuthProviderStatus, OAuthStartResult } from '@/api/oauth'
import { ApiError } from '@/api/http'

/**
 * OAuth 交互状态（仅 UI 状态；登录态仍由 useAuth 单例管理，不另建全局登录态）。
 */
const providers = ref<OAuthProviderStatus[]>([])
const providersLoading = ref(false)
const identities = ref<OAuthIdentityList | null>(null)
const identitiesLoading = ref(false)
const starting = ref<OAuthProvider | null>(null)

export function useOAuth() {
  /** 拉取平台状态（未配置时 enabled=false + reason_code，按钮显示"暂未开放"） */
  async function loadProviders(): Promise<OAuthProviderStatus[]> {
    providersLoading.value = true
    try {
      providers.value = await fetchProviders()
    } catch {
      // 状态查询失败按全部禁用展示，不阻塞密码登录
      providers.value = []
    } finally {
      providersLoading.value = false
    }
    return providers.value
  }

  /** 发起授权：成功则跳第三方授权页（整页跳转，离开本站） */
  async function begin(provider: OAuthProvider, mode: OAuthMode = 'login',
                       returnPath?: string): Promise<OAuthStartResult> {
    starting.value = provider
    try {
      const result = await startOAuth({
        provider,
        mode,
        return_path: returnPath ?? defaultReturnPath(),
      })
      // 浏览器跳第三方平台（绑定 Cookie 已由后端以 HttpOnly Cookie 下发）
      window.location.href = result.authorization_url
      return result
    } finally {
      starting.value = null
    }
  }

  /** 票据交换：login -> LoginResult（调用方写入 useAuth）；bind -> 绑定结果 */
  async function exchange(rid: string) {
    return exchangeOAuthTicket(rid)
  }

  async function loadIdentities(): Promise<OAuthIdentityList | null> {
    identitiesLoading.value = true
    try {
      identities.value = await listBoundIdentities()
    } catch {
      identities.value = null
    } finally {
      identitiesLoading.value = false
    }
    return identities.value
  }

  async function unbind(ref: string): Promise<boolean> {
    const out = await unbindIdentity(ref)
    await loadIdentities()
    return out.unbound
  }

  async function setPassword(newPassword: string) {
    return setOAuthPassword(newPassword)
  }

  const providerMap = computed(() => {
    const map: Partial<Record<OAuthProvider, OAuthProviderStatus>> = {}
    for (const p of providers.value) map[p.id] = p
    return map
  })

  return {
    providers: computed(() => providers.value),
    providerMap,
    providersLoading,
    identities: computed(() => identities.value),
    identitiesLoading,
    starting: computed(() => starting.value),
    loadProviders,
    begin,
    exchange,
    loadIdentities,
    unbind,
    setPassword,
  }
}

/** 当前站内路由（Hash 路由 path 部分），作为授权完成后的回跳目标 */
export function defaultReturnPath(): string {
  try {
    const hash = window.location.hash || ''
    const path = hash.replace(/^#/, '').split('?')[0] || '/dashboard'
    // 只允许站内业务页（与后端 return_path 白名单一致的口径）
    if (['/dashboard', '/resume', '/profile', '/jobs', '/matching',
         '/history', '/feedback', '/settings'].some(
      (p) => path === p || path.startsWith(p === '/job/' ? '/job/' : `${p}/`) ||
             (p === '/jobs' && path.startsWith('/job/')))) {
      return path
    }
  } catch {
    // 非浏览器环境忽略
  }
  return '/dashboard'
}

/** 判断错误是否为"平台未配置"（按钮据此显示提示而不是假成功） */
export function isProviderUnavailable(e: unknown): boolean {
  return e instanceof ApiError &&
    (e.code === 'OAUTH_PROVIDER_NOT_CONFIGURED' ||
     e.code === 'OAUTH_PROVIDER_DISABLED' ||
     e.code === 'OAUTH_INVALID_REDIRECT')
}
