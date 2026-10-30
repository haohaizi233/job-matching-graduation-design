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

export interface DeviceItem {
  id: number
  name: string
  place: string
  time: string
  current: boolean
}

export interface SecurityLogItem {
  id: number
  time: string
  event: string
  location: string
}

export interface SettingsState {
  nickname: string
  school: string
  major: string
  enrollYear: string
  graduateYear: string
  region: string
  theme: string
  intentTags: string[]
}
