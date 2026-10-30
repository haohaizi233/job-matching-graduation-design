export * from './resume'
export * from './profile'
export * from './jobs'
export * from './matching'
export * from './history'
export * from './feedback'
export * from './settings'

export type TrendRange = 7 | 30 | 90

export type AuthMode = 'login' | 'register' | 'reset'

export type GlyphName =
  | 'chevron'
  | 'arrow'
  | 'check'
  | 'star'
  | 'info'
  | 'file'
  | 'fileSolid'
  | 'briefcase'
  | 'eye'
  | 'eyeOff'

export interface NavItem {
  key: string
  label: string
  icon: string
  iconActive: string
  /** 已实现页面的路由地址；未实现页面仅做演示提示 */
  to?: string
}

export interface StatCardItem {
  key: string
  name: string
  value: string
  note: string
  tone: 'blue' | 'purple' | 'green' | 'orange'
  glyph: 'file' | 'plus' | 'pie' | 'star'
  trendText?: string
  trendTone?: 'green' | 'orange'
  chevron: boolean
  miniBars?: boolean
  target: string
}

export interface ProgressStep {
  title: string
  note: string
  state: 'done' | 'current' | 'future'
}

export interface JobItem {
  id: number | string
  title: string
  company: string
  tags: string[]
  salary: string
  match: number
  logo: string
  logoAlt: string
}

export interface ActivityItem {
  id: number | string
  title: string
  desc: string
  time: string
  dotTone: 'blue' | 'violet' | 'green' | 'gray'
  iconTone: 'blue' | 'purple' | 'green' | 'orange'
  glyph: 'file' | 'briefcase' | 'star'
  /** 是否绘制时间轴连接线（最后一条不画） */
  line: boolean
}

export interface NotificationItem {
  id: number | string
  text: string
}

export interface TrendDataset {
  /** 折线数据点（推荐岗位数） */
  recommended: number[]
  /** 折线数据点（高匹配岗位数） */
  highMatch: number[]
  /** 每个数据点对应的完整日期（悬浮提示用） */
  dates: string[]
  /** 横轴刻度文案 */
  axisLabels: string[]
}
