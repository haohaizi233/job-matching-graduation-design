import { apiRequest } from './http'
import type { ProfileRow, ResumeRow } from './types'

export async function listResumes(): Promise<ResumeRow[]> {
  const data = await apiRequest<{ items: ResumeRow[] }>('/resumes')
  return data.items
}

export async function getResume(resumeId: string): Promise<ResumeRow> {
  const data = await apiRequest<{ resume: ResumeRow }>(`/resumes/${resumeId}`)
  return data.resume
}

export interface ResumeUploadResult {
  resume: ResumeRow
  created: boolean
  profile: { profile: Record<string, unknown> } | null
}

/** JSON Base64 上传（前端 FileReader 转 base64 后调用，避免 multipart 差异） */
export async function uploadResumeJson(input: {
  fileName: string
  contentBase64: string
  isSynthetic?: boolean
  dataSource?: string
}): Promise<ResumeUploadResult> {
  return apiRequest<ResumeUploadResult>('/resumes/json', {
    method: 'POST',
    json: {
      file_name: input.fileName,
      content_base64: input.contentBase64,
      is_synthetic: input.isSynthetic ?? null,
      data_source: input.dataSource ?? null,
    },
  })
}

export async function deleteResume(resumeId: string): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(`/resumes/${resumeId}`, { method: 'DELETE' })
}

export async function reparseResume(
  resumeId: string,
  options: { isSynthetic?: boolean; dataSource?: string } = {},
): Promise<{ resume: ResumeRow; profile: { profile: Record<string, unknown> } | null }> {
  return apiRequest(`/resumes/${resumeId}/reparse`, {
    method: 'POST',
    json: {
      is_synthetic: options.isSynthetic ?? null,
      data_source: options.dataSource ?? null,
    },
  })
}

/** 读取文件为 base64（去掉 data:* 前缀） */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      const idx = result.indexOf(',')
      resolve(idx >= 0 ? result.slice(idx + 1) : result)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

export type { ProfileRow }
