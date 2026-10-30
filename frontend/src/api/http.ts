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
    throw new ApiError(err?.code || `HTTP_${res.status}`, err?.message || `请求失败（${res.status}）`, {
      status: res.status,
      detail: err?.detail ?? {},
      requestId: err?.request_id ?? '',
    })
  }

  return (payload as ApiEnvelope<T>).data
}
