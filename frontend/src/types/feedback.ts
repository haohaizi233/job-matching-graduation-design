export type FeedbackStatus = 'interested' | 'notInterested' | 'applied' | 'interviewed' | 'irrelevant'

export interface FeedbackRecordItem {
  id: number | string
  title: string
  company: string
  industry: string
  salary: string
  location: string
  time: string
  status: FeedbackStatus
  /** 备注（可编辑） */
  note: string
  bookmarked: boolean
  logo: string
  logoAlt: string
  /** 趋势数值（演示） */
  trend: number[]
}

export interface FeedbackStatusOption {
  label: string
  value: 'all' | FeedbackStatus
}

export interface FeedbackTrendPoint {
  label: string
  value: number
}

export interface FeedbackTrendRange {
  label: string
  value: '7d' | '30d' | '3m'
  points: FeedbackTrendPoint[]
}

export interface FeedbackStatItem {
  key: string
  label: string
  value: string
  note: string
}
