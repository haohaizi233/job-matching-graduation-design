import { apiRequest } from './http'
import type { JobRow } from './types'

export interface JobListQuery {
  category?: string
  city?: string
  status?: string
  page?: number
  pageSize?: number
}

export async function listJobs(query: JobListQuery = {}): Promise<JobRow[]> {
  const data = await listJobsPaged(query)
  return data.items
}

export interface JobPage {
  items: JobRow[]
  page: number
  pageSize: number
  total: number
}

/** 分页列表（含 total，工作台统计等需要真实总数的场景使用） */
export async function listJobsPaged(query: JobListQuery = {}): Promise<JobPage> {
  const params = new URLSearchParams()
  if (query.category) params.set('category', query.category)
  if (query.city) params.set('city', query.city)
  if (query.status) params.set('status', query.status)
  if (query.page) params.set('page', String(query.page))
  if (query.pageSize) params.set('page_size', String(query.pageSize))
  const qs = params.toString()
  return apiRequest<JobPage>(`/jobs${qs ? `?${qs}` : ''}`)
}

export async function getJob(jobId: string): Promise<JobRow> {
  const data = await apiRequest<{ job: JobRow }>(`/jobs/${jobId}`)
  return data.job
}

export async function createJob(input: {
  title: string
  jobDescription: string
  source?: string
  isSynthetic?: boolean
}): Promise<JobRow> {
  const data = await apiRequest<{ job: JobRow }>('/jobs', {
    method: 'POST',
    json: {
      title: input.title,
      job_description: input.jobDescription,
      source: input.source ?? 'manual',
      source_license: 'UNKNOWN',
      status: 'published',
      is_synthetic: input.isSynthetic ?? true,
    },
  })
  return data.job
}

export async function parseJob(jobId: string): Promise<JobRow> {
  const data = await apiRequest<{ job: JobRow }>(`/jobs/${jobId}/parse`, { method: 'POST', json: {} })
  return data.job
}
