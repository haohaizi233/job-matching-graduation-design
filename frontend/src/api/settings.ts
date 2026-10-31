/**
 * 个人设置 / 账号安全 API（Phase5-3 / M2 任务书 4.3）。
 *
 * 口径：
 *  - 用户级设置服务端持久化（/students/me/settings），主题等纯客户端偏好不上传；
 *  - 密码修改必须验证原凭证，改密后其他会话立即失效；
 *  - 登录设备管理是**真实服务端会话撤销**（非前端数组删除）。
 */
import { apiRequest } from './http'
import type { SessionItem, UserSettings, UserSettingsPatch } from '@/types/settings'

/**
 * 服务端默认设置（与后端 settings_store.DEFAULT_SETTINGS 同源）。
 * 基本资料默认留空：不伪造任何演示身份数据。
 */
export const SERVER_DEFAULT_SETTINGS: UserSettings = {
  basic: { nickname: '', school: '', major: '', enrollYear: '', graduateYear: '', region: '' },
  notifications: { siteMessage: true, emailNotice: false, matchAlert: true, weeklyReport: true },
  resume_prefs: { autoParse: true, ocrImages: false },
  privacy: { publicResume: true, companyView: true, hideSalary: false },
  job_intent: { intentTags: [] },
}

export async function getUserSettings(): Promise<UserSettings> {
  const data = await apiRequest<{ settings: UserSettings }>('/students/me/settings')
  return data.settings
}

export async function saveUserSettings(patch: UserSettingsPatch): Promise<UserSettings> {
  const data = await apiRequest<{ settings: UserSettings }>('/students/me/settings', {
    method: 'PUT',
    json: { settings: patch },
  })
  return data.settings
}

export interface ChangePasswordResult {
  password_changed: boolean
  revoked_sessions: number
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<ChangePasswordResult> {
  return apiRequest<ChangePasswordResult>('/auth/change-password', {
    method: 'POST',
    json: { old_password: oldPassword, new_password: newPassword },
  })
}

export async function listSessions(): Promise<SessionItem[]> {
  const data = await apiRequest<{ items: SessionItem[] }>('/auth/sessions')
  return data.items
}

/** 下线指定设备（真实撤销服务端会话；非本人/不存在由后端返回 404） */
export async function revokeSession(sessionId: string): Promise<void> {
  await apiRequest<{ revoked: boolean }>(`/auth/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
}

/** 一键下线其他设备（保留当前会话），返回实际撤销数量 */
export async function revokeOtherSessions(): Promise<number> {
  const data = await apiRequest<{ revoked_sessions: number }>('/auth/sessions/revoke-others', {
    method: 'POST',
  })
  return data.revoked_sessions
}
