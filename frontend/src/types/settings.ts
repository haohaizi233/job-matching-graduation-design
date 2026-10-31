/** 个人设置类型（前端 DTO 与后端 settings_store.py 分区 schema 同源）。 */

export interface SettingsToggleItem {
  key: string
  label: string
  desc: string
  value: boolean
}

export interface SettingsSelectOption {
  label: string
  value: string
}

// ---------------------------------------------------------------- 服务端设置

export interface UserSettingsBasic {
  nickname: string
  school: string
  major: string
  enrollYear: string
  graduateYear: string
  region: string
}

export interface UserSettingsNotifications {
  siteMessage: boolean
  emailNotice: boolean
  matchAlert: boolean
  weeklyReport: boolean
}

export interface UserSettingsResumePrefs {
  autoParse: boolean
  ocrImages: boolean
}

export interface UserSettingsPrivacy {
  publicResume: boolean
  companyView: boolean
  hideSalary: boolean
}

export interface UserSettingsJobIntent {
  intentTags: string[]
}

/** 服务端持久化的用户级设置（不含主题等纯客户端偏好） */
export interface UserSettings {
  basic: UserSettingsBasic
  notifications: UserSettingsNotifications
  resume_prefs: UserSettingsResumePrefs
  privacy: UserSettingsPrivacy
  job_intent: UserSettingsJobIntent
}

/** 保存请求：分区级增量（只提交给出的分区，后端按分区合并） */
export type UserSettingsPatch = Partial<UserSettings>

// ---------------------------------------------------------------- 会话（设备）

export interface SessionItem {
  session_id: string
  created_at: string | null
  last_seen_at: string | null
  expires_at: string | null
  user_agent: string
  current: boolean
}
