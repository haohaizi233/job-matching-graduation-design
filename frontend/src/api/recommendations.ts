import { apiRequest } from './http'
import { toServerFeedbackType } from './mappers'
import type { FeedbackRow, RecoHistoryPage, RecoRun, RecoRunResult } from './types'
import type { FeedbackStatus } from '@/types/feedback'

export interface RecommendInput {
  mode?: 'baseline' | 'experimental_model' | 'future_verified'
  topK?: number
  jobIds?: string[]
  category?: string
  city?: string
  modelId?: string
  allowFallback?: boolean
}

/** 发起推荐（返回 run；明细项需调 getRun 取） */
export async function createRecommendation(input: RecommendInput = {}): Promise<RecoRunResult> {
  return apiRequest<RecoRunResult>('/recommendations', {
    method: 'POST',
    json: {
      mode: input.mode ?? 'baseline',
      top_k: input.topK ?? null,
      job_ids: input.jobIds ?? null,
      category: input.category ?? null,
      city: input.city ?? null,
      model_id: input.modelId ?? null,
      allow_fallback: input.allowFallback ?? true,
    },
  })
}

/** 取推荐明细（含 items/explanation） */
export async function getRun(runId: string): Promise<RecoRun> {
  const data = await apiRequest<{ run: RecoRun }>(`/recommendations/${runId}`)
  return data.run
}

export async function listRuns(page = 1, pageSize = 20): Promise<RecoHistoryPage> {
  return apiRequest<RecoHistoryPage>(`/recommendations?page=${page}&page_size=${pageSize}`)
}

export async function submitFeedback(input: {
  runId: string
  itemId: string
  /** 前端展示态（含 pending 之外的 5 种）；映射为后端 feedback_type 枚举提交 */
  feedbackType: FeedbackStatus
  note?: string
}): Promise<FeedbackRow> {
  const data = await apiRequest<{ feedback: FeedbackRow }>(
    `/recommendations/${input.runId}/feedback`,
    {
      method: 'POST',
      json: {
        item_id: input.itemId,
        feedback_type: toServerFeedbackType(input.feedbackType),
        note: input.note ?? null,
      },
    },
  )
  return data.feedback
}

export async function listFeedback(): Promise<FeedbackRow[]> {
  const data = await apiRequest<{ items: FeedbackRow[] }>('/recommendations/feedback')
  return data.items
}
