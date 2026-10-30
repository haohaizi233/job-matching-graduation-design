import type { ApiEnvelope, ApiErrorBody } from './types'

/** 业务 API 统一错误（非 2xx 或信封内 error.code） */
export class ApiError extends Error {
  code: string
  status: number
  detail: Record<string, unknown>
  requestId: string

  constructor(
    code: string,
    message: string,
    options: { status?: number; detail?: Record<string, unknown>; requestId?: string } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = options.status ?? 0
    this.detail = options.detail ?? {}
    this.requestId = options.requestId ?? ''
  }
}

const TOKEN_KEY = 'jm_token'
const USER_KEY = 'jm_user'

/** 会话失效事件：401 清会话后广播，供全局状态（useAuth 等）同步复位 */
export const SESSION_EXPIRED_EVENT = 'jm:session-expired'

/** 失效 Token 处理：清除本地会话并回登录页（仅鉴权请求触发，登录/注册 401 不触发） */
function handleUnauthorized(): void {
  setToken('')
  setStoredUser(null)
  try {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
  } catch {
    // 非浏览器环境忽略
  }
  if (typeof window !== 'undefined' && window.location.hash !== '#/login') {
    window.location.hash = '#/login'
  }
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getStoredUser<T>(): T | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function setStoredUser(user: unknown | null): void {
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
  else localStorage.removeItem(USER_KEY)
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  /** JSON 请求体（与 body 互斥） */
  json?: unknown
  /** 原始请求体（multipart 等） */
  body?: BodyInit
  headers?: Record<string, string>
  /** 覆盖鉴权（如登录/注册传空串） */
  auth?: boolean
  signal?: AbortSignal
}

/**
 * 业务 API 请求：自动带 Bearer Token、解包 {data} 信封、错误归一为 ApiError。
 * 开发环境经 Vite 代理转发到本地后端（见 vite.config.ts 的 /api 代理）。
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', json, body, headers = {}, auth = true, signal } = options

  const finalHeaders: Record<string, string> = { Accept: 'application/json', ...headers }
  if (json !== undefined) finalHeaders['Content-Type'] = 'application/json'
  if (auth) {
    const token = getToken()
    if (token) finalHeaders.Authorization = `Bearer ${token}`
  }

  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, {
      method,
      headers: finalHeaders,
      body: json !== undefined ? JSON.stringify(json) : body,
      signal,
    })
  } catch (e) {
    throw new ApiError('NETWORK_ERROR', '网络异常，无法连接后端服务', {
      detail: { cause: String(e) },
    })
  }

  let payload: unknown = null
  const text = await res.text()
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!res.ok || (payload && typeof payload === 'object' && 'error' in payload)) {
    const err = (payload as ApiErrorBody | null)?.error
    // 失效 Token：仅当本次请求携带了鉴权且确实带了 Token 时才清会话跳登录，
    // 登录/注册接口的 401（凭证错误）不得触发跳转，避免吞掉表单错误提示。
    if (res.status === 401 && auth && getToken()) {
      handleUnauthorized()
    }
    throw new ApiError(err?.code || `HTTP_${res.status}`, err?.message || `请求失败（${res.status}）`, {
      status: res.status,
      detail: err?.detail ?? {},
      requestId: err?.request_id ?? '',
    })
  }

  return (payload as ApiEnvelope<T>).data
}
