export interface HistoryJobItem {
  id: number | string
  title: string
  company: string
  salary: string
  match: number
  logo: string
  logoAlt: string
}

export interface HistoryRecordItem {
  id: number | string
  /** 匹配时间，如 2024-10-28 14:32 */
  time: string
  profileVersion: string
  mode: string
  jobCount: number
  highMatchCount: number
  status: 'pending' | 'done' | 'expired'
  avgMatch: number
  jobs: HistoryJobItem[]
}

export interface HistoryStatusOption {
  label: string
  value: 'all' | 'done' | 'expired' | 'pending'
}
