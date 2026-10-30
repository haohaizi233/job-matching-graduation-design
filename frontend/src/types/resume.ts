export interface ResumeStat {
  key: string
  name: string
  value: string
  note: string
  tone: 'blue' | 'green' | 'orange' | 'red'
  icon: 'file' | 'check' | 'clock' | 'alert'
}

export interface ResumeItem {
  id: number | string
  filename: string
  filesize: string
  uploadDate: string
  status: 'done' | 'partial' | 'retry' | 'running'
  statusText: string
  statusNote?: string
  version: string
  versionDate: string
  source: string
  fileType: 'pdf' | 'word'
}

export interface WorkflowStep {
  step: number
  title: string
  desc: string
  icon: string
  tone: 'blue' | 'green'
}

export interface FAQItem {
  id: number | string
  question: string
  answer: string
  extra: string
}
