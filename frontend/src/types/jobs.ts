export interface JobFilterOption {
  label: string
  value: string
}

export interface JobCardItem {
  id: number | string
  title: string
  company: string
  industry: string
  scale: string
  location: string
  publishTime: string
  salary: string
  months: number
  match: number
  education: string
  experience: string
  tags: string[]
  desc: string
  logo: string
  logoAlt: string
  category: string
}

export interface JobDutyGroup {
  title: string
  icon: 'duty' | 'require' | 'skill' | 'company'
  items?: string[]
  skillGroups?: { group: string; skills: string[] }[]
}

export interface JobDetailData {
  id: number | string
  title: string
  company: string
  industry: string
  scale: string
  status: string
  location: string
  education: string
  publishTime: string
  salary: string
  months: number
  tags: string[]
  logo: string
  logoAlt: string
  matchPreview: {
    percent: number
    level: string
    desc: string
  }
  skillMatch: {
    matched: string[]
    improve: string[]
  }
  conditionMatch: { label: string; value: string }[]
  advice: string[]
  duties: string[]
  requirements: string[]
  skillGroups: { group: string; skills: string[] }[]
  companyIntro: string
}

export interface SelectedFilter {
  key: string
  label: string
}
