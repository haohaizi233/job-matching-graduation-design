export interface ProfileRadarData {
  dimensions: string[]
  scores: number[]
  avgScores: number[]
}

export interface ProfileSkill {
  name: string
  level: string
}

export interface ProfileEducation {
  school: string
  major: string
  degree: string
  period: string
  gpa: string
  ranking: string
}

export interface ProfileProject {
  id: number
  name: string
  role: string
  period: string
  highlights: string[]
}

export interface ProfileInternship {
  id: number
  company: string
  position: string
  period: string
  location: string
  highlights: string[]
}
