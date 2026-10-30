/**
 * 后端 DTO → 前端视图类型的映射层。
 * 后端（Phase5-2）只存业务事实（标题/JD/解析画像/评分解释），
 * 视图需要的展示字段（企业、薪资、标签等）在此做降级推导：
 * 有值取值，无值给占位，不伪造数据来源。
 */
import genericLogo from '@/assets/icons/company/generic-globe.png'

import type {
  FeedbackRow,
  JobRow,
  ProfileFieldValue,
  ProfileRow,
  RecoItem,
  RecoRun,
  ResumeRow,
} from './types'
import type {
  FeedbackRecordItem,
  FeedbackStatus,
  HistoryRecordItem,
  JobCardItem,
  JobDetailData,
  MatchJobItem,
  MatchReason,
  ProfileEducation,
  ProfileInternship,
  ProfileProject,
  ProfileSkill,
  ResumeItem,
} from '@/types'

export const GENERIC_LOGO = genericLogo

type AnyDict = Record<string, unknown>

// ---------------------------------------------------------------- 小工具

function asDict(v: unknown): AnyDict {
  return v && typeof v === 'object' ? (v as AnyDict) : {}
}

/** 取画像字段的 value（字段形如 {value, status, evidence_text, ...}） */
export function pickValue(source: AnyDict, key: string): unknown {
  const f = source[key]
  if (f && typeof f === 'object' && 'value' in (f as AnyDict)) {
    return (f as ProfileFieldValue).value
  }
  return f
}

function pickText(source: AnyDict, key: string, fallback = ''): string {
  const v = pickValue(source, key)
  return v === null || v === undefined ? fallback : String(v)
}

function textOf(v: unknown, fallback = ''): string {
  return v === null || v === undefined ? fallback : String(v)
}

/** "2026-10-30T10:01:47.743734" → "2026-10-30" */
export function dateOnly(iso: string | null | undefined): string {
  return textOf(iso).slice(0, 10)
}

/** "2026-10-30T10:01:47" → "2026-10-30 10:01" */
export function dateTime(iso: string | null | undefined): string {
  const s = textOf(iso)
  return s ? `${s.slice(0, 10)} ${s.slice(11, 16)}` : ''
}

function fileSizeText(bytes: number): string {
  if (!bytes) return '0 KB'
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** 技能条目可能是字符串或 SkillEntry 对象 */
export function skillName(s: unknown): string {
  if (typeof s === 'string') return s
  const d = asDict(s)
  return textOf(d.canonical_name || d.name || d.raw_form)
}

function skillNames(list: unknown): string[] {
  return (Array.isArray(list) ? list : []).map(skillName).filter(Boolean)
}

const CATEGORY_LABELS: Record<string, string> = {
  'INFORMATION-TECHNOLOGY': '互联网 / IT',
  FINANCE: '金融',
  EDUCATION: '教育',
  MANUFACTURING: '制造业',
}

const CATEGORY_CODE: Record<string, string> = {
  'INFORMATION-TECHNOLOGY': 'backend',
  FINANCE: 'data',
  EDUCATION: 'pm',
  MANUFACTURING: 'algorithm',
}

const EDUCATION_LABELS: Record<string, string> = {
  本科: '本科及以上',
  硕士: '硕士及以上',
  博士: '博士',
  大专: '大专及以上',
}

// ---------------------------------------------------------------- 岗位

export interface JobProfileView {
  employer: string
  city: string
  salary: string
  category: string
  categoryLabel: string
  education: string
  experience: string
  requiredSkills: string[]
  preferredSkills: string[]
  responsibilities: string[]
  duties: string[]
  requirements: string[]
}

/** 解析 JobRow（含 structured_profile）为展示字段集 */
export function jobProfileView(job: JobRow): JobProfileView {
  const sp = asDict(job.structured_profile)
  const employer = pickText(sp, 'employer') || '未标注企业'
  const city = pickText(sp, 'city') || textOf(job.city) || '全国'
  const salary = pickText(sp, 'salary') || '面议'
  const categoryRaw = textOf(job.job_category) || pickText(sp, 'job_category') || ''
  const categoryLabel = CATEGORY_LABELS[categoryRaw] || '互联网 / IT'

  const eduReq = asDict(sp.education_requirement)
  const education =
    EDUCATION_LABELS[textOf(job.education_min)] ||
    textOf(eduReq.raw) ||
    textOf(job.education_min) ||
    '学历要求未标注'

  const expReq = asDict(sp.experience_requirement)
  const expYears = expReq.years_min
  const experience = expYears ? `${textOf(expYears)} 年以上经验` : '经验不限'

  const requiredSkills = skillNames(sp.required_skills)
  const preferredSkills = skillNames(sp.preferred_skills)

  const respField = asDict(sp.responsibilities)
  const respText = pickText(sp, 'responsibilities') || textOf(respField.evidence_text)
  const responsibilities = respText
    ? respText.split(/\n|；|;/).map((s) => s.trim()).filter(Boolean)
    : []

  // JD 原文按分号/换行拆条，作为职责/要求的兜底展示
  const jdLines = textOf(job.job_description)
    .split(/\n|；|;/)
    .map((s) => s.replace(/^[•\-·\s]+/, '').trim())
    .filter(Boolean)

  return {
    employer,
    city,
    salary,
    category: CATEGORY_CODE[categoryRaw] || 'backend',
    categoryLabel,
    education,
    experience,
    requiredSkills,
    preferredSkills,
    responsibilities,
    duties: responsibilities.length ? responsibilities : jdLines,
    requirements: jdLines,
  }
}

/** JobRow → 岗位卡片（matchScore 0-100，未跑推荐时为 0） */
export function mapJobToCard(job: JobRow, matchScore = 0): JobCardItem {
  const v = jobProfileView(job)
  const tags = [...v.requiredSkills, ...v.preferredSkills].slice(0, 5)
  return {
    id: job.id,
    title: job.title,
    company: v.employer,
    industry: v.categoryLabel,
    scale: '—',
    location: v.city,
    publishTime: dateOnly(job.created_at),
    salary: v.salary,
    months: 0,
    match: Math.round(matchScore),
    education: v.education,
    experience: v.experience,
    tags: tags.length ? tags : [v.categoryLabel],
    desc: textOf(job.job_description).slice(0, 90),
    logo: GENERIC_LOGO,
    logoAlt: v.employer,
    category: v.category,
  }
}

/** JobRow → 岗位详情（matchPreview/skillMatch/advice 由推荐解释提供，无则占位） */
export function mapJobToDetail(
  job: JobRow,
  options: {
    matchScore?: number
    matched?: string[]
    missing?: string[]
    explanation?: RecoItem['explanation_snapshot']
  } = {},
): JobDetailData {
  const v = jobProfileView(job)
  const match = Math.round(options.matchScore ?? 0)
  const level = match >= 80 ? '高度匹配' : match >= 60 ? '较匹配' : match > 0 ? '一般' : '待评估'
  const matched = options.matched ?? []
  const missing = options.missing ?? []

  const conditionMatch = [
    { label: '学历要求', value: v.education },
    { label: '经验要求', value: v.experience },
    { label: '工作城市', value: v.city },
    { label: '招聘企业', value: v.employer },
  ]

  const advice: string[] = []
  if (missing.length) advice.push(`优先补齐岗位硬性技能：${missing.slice(0, 3).join('、')}`)
  if (!missing.length && matched.length) advice.push('核心技能已覆盖，可在简历中突出相关项目成果')
  advice.push('投递前对照岗位职责润色简历关键词，提高筛选通过率')

  return {
    id: job.id,
    title: job.title,
    company: v.employer,
    industry: v.categoryLabel,
    scale: '—',
    status: job.status === 'published' ? '招聘中' : job.status,
    location: v.city,
    education: v.education,
    publishTime: dateOnly(job.created_at),
    salary: v.salary,
    months: 0,
    tags: [...v.requiredSkills, ...v.preferredSkills].slice(0, 6),
    logo: GENERIC_LOGO,
    logoAlt: v.employer,
    matchPreview: {
      percent: match,
      level,
      desc:
        match > 0
          ? `基于你的画像与岗位解析结果，综合匹配度 ${match}%（排序参考分，非录用概率）`
          : '尚未针对该岗位运行匹配，先看看岗位要求吧',
    },
    skillMatch: { matched, improve: missing },
    conditionMatch,
    advice,
    duties: v.duties.length ? v.duties : ['岗位暂未提供明确职责描述'],
    requirements: v.requirements.length ? v.requirements : ['岗位暂未提供明确任职要求'],
    skillGroups: [
      { group: '硬性技能', skills: v.requiredSkills.length ? v.requiredSkills : ['JD 未标注'] },
      { group: '加分技能', skills: v.preferredSkills.length ? v.preferredSkills : ['JD 未标注'] },
    ],
    companyIntro: `${v.employer}（企业信息由岗位 JD 提供，未标注项不作推断）`,
  }
}

// ---------------------------------------------------------------- 推荐

const REASON_LABELS: Record<MatchReason['key'], string> = {
  skill: '技能覆盖',
  education: '教育匹配',
  project: '项目相关性',
  intent: '求职意向',
}

function reasonScoreFromStatus(status: string): number {
  if (status === 'ok') return 90
  if (status === 'requirement_unclear' || status === 'unknown') return 60
  return 40
}

/** 推荐解释 → 匹配理由条目 */
export function explanationToReasons(exp: RecoItem['explanation_snapshot']): MatchReason[] {
  const matched = skillNames(exp.matched_skills)
  const missing = skillNames(exp.missing_required_skills)
  const skillScore = Math.max(
    20,
    Math.round((matched.length / Math.max(1, matched.length + missing.length)) * 100),
  )

  const edu = asDict(exp.education_constraint)
  const expc = asDict(exp.experience_constraint)
  const cohort = asDict(exp.graduation_cohort_constraint)

  return [
    {
      key: 'skill',
      label: REASON_LABELS.skill,
      score: matched.length || missing.length ? skillScore : 65,
    },
    {
      key: 'education',
      label: REASON_LABELS.education,
      score: reasonScoreFromStatus(textOf(edu.status, 'unknown')),
    },
    {
      key: 'project',
      label: REASON_LABELS.project,
      score: reasonScoreFromStatus(textOf(expc.status, 'unknown')),
    },
    {
      key: 'intent',
      label: REASON_LABELS.intent,
      score: reasonScoreFromStatus(textOf(cohort.status, 'unknown')),
    },
  ]
}

/** RecoItem（+岗位行） → 匹配卡片 */
export function mapRecoToMatchItem(item: RecoItem, job?: JobRow | null): MatchJobItem {
  const exp = asDict(item.explanation_snapshot) as unknown as RecoItem['explanation_snapshot']
  const v = job ? jobProfileView(job) : null
  const match = Math.round(item.score * 100)
  const missing = skillNames(exp.missing_required_skills)
  const matched = skillNames(exp.matched_skills)
  const potential = Math.max(30, Math.min(95, match + Math.round(missing.length * 4) + 12))

  return {
    id: item.job_id,
    title: job?.title || textOf((exp as unknown as AnyDict).job_title) || '未命名岗位',
    company: v?.employer || '未标注企业',
    industry: v?.categoryLabel || '互联网 / IT',
    location: v?.city || '全国',
    salary: v?.salary || '面议',
    months: 0,
    match,
    potential,
    tags: (v ? [...v.requiredSkills, ...v.preferredSkills] : matched).slice(0, 5),
    reasons: explanationToReasons(exp),
    missingSkills: missing,
    logo: GENERIC_LOGO,
    logoAlt: v?.employer || '未标注企业',
    category: v?.category || 'backend',
  }
}

// ---------------------------------------------------------------- 推荐历史

/** RecoRun → 历史记录卡片（jobs 明细由调用方补齐） */
export function mapRunToHistory(run: RecoRun): HistoryRecordItem {
  const snapshot = Array.isArray(run.job_set_snapshot) ? run.job_set_snapshot : []
  return {
    id: run.id,
    time: dateTime(run.created_at),
    profileVersion: `画像 v${run.profile_version ?? 1}`,
    mode: run.scoring_method === 'baseline_skill_text_v1' ? '基线匹配' : run.scoring_method,
    jobCount: snapshot.length,
    highMatchCount: 0,
    status: 'done',
    avgMatch: 0,
    jobs: [],
  }
}

// ---------------------------------------------------------------- 反馈

const FEEDBACK_STATUS: FeedbackStatus[] = [
  'interested',
  'notInterested',
  'applied',
  'interviewed',
  'irrelevant',
]

export function mapFeedbackToRecord(
  fb: FeedbackRow,
  job?: JobRow | null,
  _item?: RecoItem | null,
): FeedbackRecordItem {
  const status: FeedbackStatus = FEEDBACK_STATUS.includes(fb.feedback_type as FeedbackStatus)
    ? (fb.feedback_type as FeedbackStatus)
    : 'interested'
  const v = job ? jobProfileView(job) : null
  return {
    id: fb.id,
    title: job?.title || '推荐岗位',
    company: v?.employer || '未标注企业',
    industry: v?.categoryLabel || '互联网 / IT',
    salary: v?.salary || '面议',
    location: v?.city || '全国',
    time: dateTime(fb.created_at),
    status,
    note: fb.note || '',
    bookmarked: status === 'interested',
    logo: GENERIC_LOGO,
    logoAlt: v?.employer || '未标注企业',
    trend: [],
  }
}

// ---------------------------------------------------------------- 简历

const RESUME_STATUS: Record<string, ResumeItem['status']> = {
  ok: 'done',
  partial: 'partial',
  failed: 'retry',
  running: 'running',
}

export function mapResumeToItem(row: ResumeRow): ResumeItem {
  const status = RESUME_STATUS[row.parse_status] || 'partial'
  const statusText =
    status === 'done' ? '解析完成' : status === 'partial' ? '部分解析' : status === 'retry' ? '解析失败' : '解析中'
  return {
    id: row.id,
    filename: row.original_filename,
    filesize: fileSizeText(row.file_size),
    uploadDate: dateOnly(row.uploaded_at),
    status,
    statusText,
    statusNote: row.parse_error || undefined,
    version: `v${row.profile_version ?? 1}`,
    versionDate: dateOnly(row.updated_at),
    source: row.data_source === 'synthetic' ? '合成数据' : row.data_source,
    fileType: /\.docx?$/i.test(row.original_filename) ? 'word' : 'pdf',
  }
}

// ---------------------------------------------------------------- 画像

interface ExperienceLike {
  id: number
  name: string
  role: string
  period: string
  highlights: string[]
}

function mapExperiences(list: unknown, fallbackRole: string): ExperienceLike[] {
  return (Array.isArray(list) ? list : []).map((raw, index) => {
    const d = asDict(raw)
    const highlights = Array.isArray(d.quantified_achievements)
      ? (d.quantified_achievements as unknown[]).map((x) => textOf(x))
      : []
    const excerpt = textOf(d.excerpt)
    return {
      id: index + 1,
      name: textOf(d.title || d.name, '未命名经历'),
      role: fallbackRole,
      period: textOf(d.period),
      highlights: highlights.length ? highlights : excerpt ? [excerpt.slice(0, 60)] : ['暂无补充说明'],
    }
  })
}

export function mapProfileSkills(row: ProfileRow | null): ProfileSkill[] {
  const skills = row?.profile_data?.profile?.skills
  return (Array.isArray(skills) ? skills : []).map((s) => {
    const d = asDict(s)
    const confidence = typeof d.confidence === 'number' ? d.confidence : 0.7
    return {
      name: skillName(s),
      level: confidence >= 0.85 ? '熟练' : confidence >= 0.7 ? '掌握' : '了解',
    }
  })
}

export function mapProfileEducation(row: ProfileRow | null): ProfileEducation {
  const prof = asDict(row?.profile_data?.profile)
  return {
    school: '示例大学',
    major: pickText(prof, 'major', '未填写'),
    degree: pickText(prof, 'education_level', '未填写'),
    period: `${textOf(pickValue(prof, 'graduation_year'), '未填写')} 届`,
    gpa: '—',
    ranking: '—',
  }
}

export function mapProfileProjects(row: ProfileRow | null): ProfileProject[] {
  return mapExperiences(row?.profile_data?.profile?.project_experiences, '项目成员').map((e) => ({
    id: e.id,
    name: e.name,
    role: e.role,
    period: e.period,
    highlights: e.highlights,
  }))
}

export function mapProfileInternships(row: ProfileRow | null): ProfileInternship[] {
  return mapExperiences(row?.profile_data?.profile?.internship_experiences, '实习生').map((e) => ({
    id: e.id,
    company: e.name,
    position: e.role,
    period: e.period,
    location: '—',
    highlights: e.highlights,
  }))
}
