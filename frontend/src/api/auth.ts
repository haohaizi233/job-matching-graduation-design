import { apiRequest } from './http'
import type { AuthUser, LoginResult } from './types'

export async function register(username: string, password: string, email?: string): Promise<AuthUser> {
  const data = await apiRequest<{ user: AuthUser }>('/auth/register', {
    method: 'POST',
    json: { username, password, email: email || null },
    auth: false,
  })
  return data.user
}

export async function login(username: string, password: string): Promise<LoginResult> {
  return apiRequest<LoginResult>('/auth/login', {
    method: 'POST',
    json: { username, password },
    auth: false,
  })
}

export async function logout(): Promise<boolean> {
  const data = await apiRequest<{ revoked: boolean }>('/auth/logout', { method: 'POST' })
  return data.revoked
}

export async function fetchMe(): Promise<AuthUser> {
  const data = await apiRequest<{ user: AuthUser }>('/auth/me')
  return data.user
}
