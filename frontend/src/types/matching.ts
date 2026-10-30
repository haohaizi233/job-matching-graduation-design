export interface MatchFilterOption {
  label: string
  value: string
}

export type MatchMode = '综合推荐' | '高匹配优先' | '高潜力优先'

export interface MatchModeOption {
  key: MatchMode
  label: string
  desc: string
}

export interface MatchReason {
  /** 技能覆盖 / 学历匹配 / 项目相关性 / 求职意向一致 */
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
  /** 学历要求（岗位侧） */
  education?: string
  /** 经验要求（岗位侧） */
  experience?: string
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

export interface MatchDistributionSlice {
  label: string
  value: number
  color: string
}

export interface MatchCategoryStat {
  label: string
  value: number
  /** 占比（%） */
  percent: number
}
