/**
 * 后端业务 API（Phase5-2 business_api）的数据传输对象。
 * 与 `src/types` 中的视图类型分开：视图类型服务于 UI，本文件只描述线上契约。
 */

/** 统一成功信封 */
export interface ApiEnvelope<T> {
  request_id: string
  api_version: string
  app_version: string
  data: T
  warnings: string[]
}

/** 统一错误信封 */
export interface ApiErrorBody {
  error: {
    code: string
    message: string
    request_id: string
    detail: Record<string, unknown>
  }
}

export interface AuthUser {
  id: string
  username: string
  email: string | null
  role: 'student' | 'admin'
  status: string
  created_at: string
}

export interface LoginResult {
  token: string
  user: AuthUser
  token_type: string
  expires_at: string
  session_id: string
}

/** 画像字段（抽取值 + 证据元信息） */
export interface ProfileFieldValue {
  value: unknown
  status?: string
  fact_source?: string
  extraction_method?: string
  evidence_text?: string
  note?: string
}

export interface ProfileData {
  profile: Record<string, ProfileFieldValue> & {
    profile_id?: string
    parse_status?: string
    skills?: unknown
    experiences?: unknown
  }
  user_edits?: Record<string, unknown>
  extraction_snapshot?: unknown
  data_source?: string
}

export interface ProfileRow {
  id: string
  user_id: string
  profile_version: number
  confirmed: boolean
  resume_id: string | null
  profile_data: ProfileData
  created_at?: string
}

export interface ResumeRow {
  id: string
  original_filename: string
  storage_key: string
  file_sha256: string
  file_size: number
  parse_status: string
  parse_error: string | null
  profile_version: number | null
  data_source: string
  data_source_declared: boolean
  uploaded_at: string
  updated_at: string
}

export interface JobRow {
  id: string
  title: string
  job_description: string
  source: string
  source_license: string
  status: string
  job_category: string | null
  city: string | null
  education_min: string | null
  created_at: string
  updated_at: string
  profile_parsed: boolean
  profile_status: string
  profile_error: string | null
  parser_version: string | null
  profile_current: boolean
  data_source: string
  structured_profile?: Record<string, unknown> | null
}

/** 推荐明细解释快照（explanation_snapshot） */
export interface RecoExplanation {
  job_id: string
  rank: number
  score: number
  score_type: string
  scoring_method?: string
  model_version?: string
  matched_skills?: string[]
  missing_required_skills?: string[]
  preferred_skills_missing?: string[]
  education_constraint?: Record<string, unknown>
  experience_constraint?: Record<string, unknown>
  graduation_cohort_constraint?: Record<string, unknown>
  warnings?: string[]
}

export interface RecoItem {
  id: string
  job_id: string
  rank: number
  score: number
  score_type: string
  explanation_snapshot: RecoExplanation
}

export interface RecoRun {
  id: string
  user_id: string
  resume_id: string | null
  profile_version: number | null
  scoring_method: string
  model_version: string
  scoring_config_version: string
  job_set_snapshot: Array<Record<string, unknown>>
  created_at: string
  /** 模型不可用显式降级快照（未降级为 null） */
  degradation_info?: {
    degraded: boolean
    reason_code?: string
    failure_kind?: string
    requested_model_id?: string
    actual_scoring_method?: string
  } | null
  items?: RecoItem[]
}

export interface RecoRunResult {
  run: RecoRun
  created: boolean
  result_summary?: {
    mode?: string
    scoring_method?: string
    score_type?: string
    model_version?: string
    evaluation_status?: string
    formal_evaluation?: boolean
    degradation?: RecoRun['degradation_info']
    warnings?: string[]
  }
}

export interface RecoHistoryPage {
  items: RecoRun[]
  page: number
  page_size: number
  total: number
}

export interface FeedbackRow {
  id: string
  recommendation_item_id: string
  feedback_type: string
  note: string | null
  created_at: string
}
