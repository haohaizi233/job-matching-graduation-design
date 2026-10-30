import { reactive, readonly } from 'vue'

import { fetchMe, login as apiLogin, logout as apiLogout, register as apiRegister } from '@/api/auth'
import { getStoredUser, getToken, setStoredUser, setToken } from '@/api/http'
import type { AuthUser } from '@/api/types'

interface AuthState {
  user: AuthUser | null
  token: string
  /** 是否已尝试从本地恢复会话 */
  restored: boolean
}

const state = reactive<AuthState>({
  user: getStoredUser<AuthUser>(),
  token: getToken(),
  restored: false,
})

/** 全局登录态（单例）：token 持久化在 localStorage，用户信息随登录写入 */
export function useAuth() {
  async function login(username: string, password: string): Promise<AuthUser> {
    const result = await apiLogin(username, password)
    state.token = result.token
    state.user = result.user
    setToken(result.token)
    setStoredUser(result.user)
    return result.user
  }

  async function register(username: string, password: string, email?: string): Promise<AuthUser> {
    return apiRegister(username, password, email)
  }

  async function logout(): Promise<void> {
    try {
      if (state.token) await apiLogout()
    } catch {
      // 登出失败也清本地会话，避免卡在失效 token 上
    }
    state.token = ''
    state.user = null
    setToken('')
    setStoredUser(null)
  }

  /** 页面刷新后校验 token 是否仍有效（失效则清会话） */
  async function restore(): Promise<boolean> {
    if (!state.token) {
      state.restored = true
      return false
    }
    try {
      state.user = await fetchMe()
      setStoredUser(state.user)
      return true
    } catch {
      state.token = ''
      state.user = null
      setToken('')
      setStoredUser(null)
      return false
    } finally {
      state.restored = true
    }
  }

  return {
    state: readonly(state),
    login,
    register,
    logout,
    restore,
  }
}
