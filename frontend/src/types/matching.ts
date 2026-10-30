export interface MatchFilterOption {
  label: string
  value: string
}

export type MatchMode = '综合排序' | '高匹配优先' | '高潜力优先'

export interface MatchReason {
  /** 技能覆盖 / 教育匹配 / 项目相关性 / 求职意向 */
  key: 'skill' | 'education' | 'project' | 'intent'
  label: string
  score: number
}

export interface MatchJobItem {
  id: number | string
  title: string
  company: string
  industry: string
  location: string
  salary: string
  months: number
  /** 综合匹配度 0-100 */
  match: number
  /** 潜力分（高潜力排序用） */
  potential: number
  tags: string[]
  reasons: MatchReason[]
  /** 待补充技能 */
  missingSkills: string[]
  logo: string
  logoAlt: string
  category: string
}

export interface MatchOverview {
  avgMatch: number
  highMatchCount: number
  coveredSkills: number
  totalSkills: number
}

export interface MatchDistributionSlice {
  label: string
  value: number
  color: string
}

export interface MatchCategoryStat {
  label: string
  value: number
}
