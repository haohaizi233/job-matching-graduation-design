/**
 * 工作台真实数据聚合层。
 *
 * 口径（Phase5-3 / M2）：
 *  - 所有统计值来自真实业务 API，**不使用任何 Mock 数据填补**；
 *  - 复用已有端点（/students/me/profile、/resumes、/jobs、/recommendations、
 *    /recommendations/feedback），不新增后端聚合接口；
 *  - 无业务数据源的指标（如"较上周 +12%"）**不伪造**，直接标注来源未实现并展示空态；
 *  - 推荐分数是启发式/研究匹配分，**不是录用概率**，展示层必须带免责说明。
 */
import { listFeedback, listRuns } from './recommendations'
import { listJobsPaged } from './jobs'
import { getProfile } from './profile'
import { listResumes } from './resumes'
import { ApiError } from './http'
import { dateTime, mapRecoToMatchItem, mapRunToHistory } from './mappers'
import type { JobRow, ProfileRow, RecoRun, ResumeRow } from './types'
import type {
  ActivityItem,
  JobItem,
  NotificationItem,
  ProgressStep,
  StatCardItem,
} from '@/types'

// ---------------------------------------------------------------- 时间展示

/** ISO 时间 → 「今天 10:24」/「昨天 16:20」/「10-19 20:17」 */
export function relativeTime(iso: string | null | undefined, now = new Date()): string {
  const s = String(iso || '')
  if (!s) return ''
  const d = new Date(s.replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return dateTime(iso)
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const day = 24 * 3600 * 1000
  const t = d.getTime()
  if (t >= startOfToday) return `今天 ${hm}`
  if (t >= startOfToday - day) return `昨天 ${hm}`
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}  ${hm}`
}

// ---------------------------------------------------------------- 原始数据

export interface DashboardSource {
  resumes: ResumeRow[]
  profile: ProfileRow | null
  jobTotal: number
  runs: RecoRun[]
  runTotal: number
  feedbackCount: number
  /** 单项数据源不可用时的说明（真实登记，不静默吞掉） */
  notes: string[]
}

async function settle<T>(label: string, p: Promise<T>, fallback: T,
                         notes: string[]): Promise<T> {
  try {
    return await p
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) throw e // 未认证必须上抛，不降级
    notes.push(`${label}暂不可用（${e instanceof ApiError ? e.code : 'NETWORK_ERROR'}）`)
    return fallback
  }
}

export async function fetchDashboardSource(): Promise<DashboardSource> {
  const notes: string[] = []
  const [resumes, profile, jobPage, runPage, feedback] = await Promise.all([
    settle('简历列表', listResumes(), [] as ResumeRow[], notes),
    settle('个人画像', getProfile(), null as ProfileRow | null, notes),
    settle('岗位列表', listJobsPaged({ page: 1, pageSize: 1 }),
           { items: [], page: 1, pageSize: 1, total: 0 }, notes),
    settle('推荐历史', listRuns(1, 10), { items: [], page: 1, page_size: 10, total: 0 }, notes),
    settle('岗位反馈', listFeedback(), [], notes),
  ])
  return {
    resumes,
    profile,
    jobTotal: jobPage.total,
    runs: runPage.items ?? [],
    runTotal: runPage.total ?? (runPage.items?.length ?? 0),
    feedbackCount: feedback.length,
    notes,
  }
}

// ---------------------------------------------------------------- 统计卡片

export function buildStatCards(src: DashboardSource): StatCardItem[] {
  const latest = [...src.resumes].sort((a, b) =>
    String(b.uploaded_at).localeCompare(String(a.uploaded_at)))[0]

  const resumeValue = !latest
    ? '暂无简历'
    : latest.parse_status === 'ok'
      ? '已完成'
      : latest.parse_status === 'pending'
        ? '解析中'
        : latest.parse_status === 'failed' || latest.parse_status === 'ocr_required'
          ? '解析失败'
          : latest.parse_status === 'partial'
            ? '部分解析'
            : '待处理'

  const profileValue = src.profile ? `v${src.profile.profile_version}` : '暂无画像'
  const profileNote = src.profile
    ? `更新于：${String(src.profile.created_at || '').slice(0, 10)}`
    : '上传简历后自动生成'

  return [
    {
      key: 'resume',
      name: '简历状态',
      value: resumeValue,
      note: latest ? `最后更新：${String(latest.uploaded_at || '').slice(0, 10)}` : '尚未上传简历',
      tone: 'blue',
      glyph: 'file',
      chevron: true,
      target: '简历管理',
    },
    {
      key: 'profile',
      name: '当前画像版本',
      value: profileValue,
      note: profileNote,
      tone: 'purple',
      glyph: 'plus',
      chevron: true,
      target: '我的画像',
    },
    {
      key: 'jobs',
      name: '可投递岗位',
      value: src.jobTotal.toLocaleString('zh-CN'),
      // 「较上周 +12%」需要历史快照，当前业务库无该数据源 -> 不伪造，明确标注
      note: '已发布岗位总数（暂无周环比数据源）',
      tone: 'green',
      glyph: 'pie',
      chevron: false,
      target: '岗位探索',
    },
    {
      key: 'matching',
      name: '最近推荐',
      value: String(src.runTotal),
      note: `累计推荐运行 ${src.runTotal} 次`,
      tone: 'orange',
      glyph: 'star',
      chevron: true,
      target: '智能匹配',
    },
  ]
}

// ---------------------------------------------------------------- 求职进度

export function buildProgressSteps(src: DashboardSource): ProgressStep[] {
  const hasResume = src.resumes.length > 0
  const resumeOk = src.resumes.some((r) => r.parse_status === 'ok' || r.parse_status === 'partial')
  const hasProfile = Boolean(src.profile)
  const confirmed = Boolean(src.profile?.confirmed)
  const hasRun = src.runTotal > 0
  const hasFeedback = src.feedbackCount > 0

  const state = (done: boolean, current: boolean): ProgressStep['state'] =>
    done ? 'done' : current ? 'current' : 'future'

  return [
    {
      title: '上传简历',
      note: hasResume ? '已完成' : '待完成',
      state: state(hasResume, !hasResume),
    },
    {
      title: '解析画像',
      note: resumeOk ? '已完成' : hasResume ? '解析中' : '待完成',
      state: state(resumeOk, hasResume && !resumeOk),
    },
    {
      title: '确认画像',
      note: confirmed ? '已完成' : hasProfile ? '进行中' : '待完成',
      state: state(confirmed, hasProfile && !confirmed),
    },
    {
      title: '智能推荐',
      note: hasRun ? '已完成' : confirmed ? '进行中' : '待完成',
      state: state(hasRun, confirmed && !hasRun),
    },
    {
      title: '反馈岗位',
      note: hasFeedback ? '已完成' : hasRun ? '进行中' : '待完成',
      state: state(hasFeedback, hasRun && !hasFeedback),
    },
  ]
}

export interface ProgressStatus {
  title: string
  note: string
  percent: number
}

export function buildProgressStatus(src: DashboardSource): ProgressStatus {
  const steps = buildProgressSteps(src)
  const done = steps.filter((s) => s.state === 'done').length
  const percent = Math.round((done / steps.length) * 100)
  const current = steps.find((s) => s.state === 'current')

  if (!current) {
    return {
      title: '求职闭环已全部完成',
      note: '可继续上传新简历或发起新的推荐',
      percent: 100,
    }
  }
  const titles: Record<string, [string, string]> = {
    上传简历: ['等待你上传简历', '上传后系统会自动抽取能力画像'],
    解析画像: ['正在解析你的简历内容', '解析完成后可人工校正画像字段'],
    确认画像: ['正在等待你确认当前画像', '确认后推荐结果才会锁定该版本'],
    智能推荐: ['等待发起岗位推荐', '确认画像后即可一键生成推荐'],
    反馈岗位: ['等待你对推荐结果反馈', '反馈会进入推荐历史，便于复盘'],
  }
  const [title, note] = titles[current.title] ?? ['任务进行中', '请继续完成当前步骤']
  return { title, note, percent }
}

// ---------------------------------------------------------------- 推荐岗位

/** 推荐卡片：只读取真实推荐运行结果，无推荐时返回空数组（由视图展示空态） */
export async function buildRecommendJobs(src: DashboardSource): Promise<JobItem[]> {
  const latest = [...src.runs].sort((a, b) =>
    String(b.created_at).localeCompare(String(a.created_at)))[0]
  if (!latest) return []

  let run = latest
  if (!Array.isArray(latest.items) || latest.items.length === 0) {
    try {
      const { getRun } = await import('./recommendations')
      run = await getRun(latest.id)
    } catch {
      return []
    }
  }
  const items = (run.items ?? []).slice().sort((a, b) => a.rank - b.rank).slice(0, 4)
  if (!items.length) return []

  const jobIds = [...new Set(items.map((i) => i.job_id))]
  const jobMap = new Map<string, JobRow | null>()
  await Promise.all(jobIds.map(async (id) => {
    try {
      const { getJob } = await import('./jobs')
      jobMap.set(id, await getJob(id))
    } catch {
      jobMap.set(id, null) // 岗位已下线/删除时保留解释，不伪造岗位信息
    }
  }))

  return items.map((item) => {
    const job = jobMap.get(item.job_id) ?? null
    const mapped = mapRecoToMatchItem(item, job)
    return {
      id: item.job_id,
      title: mapped.title,
      company: mapped.company,
      tags: [mapped.location, mapped.industry].filter(Boolean).slice(0, 3),
      salary: mapped.salary,
      match: mapped.match,
      logo: mapped.logo,
      logoAlt: mapped.logoAlt,
    } satisfies JobItem
  })
}

// ---------------------------------------------------------------- 最近活动

export function buildActivityItems(src: DashboardSource): ActivityItem[] {
  type Row = { at: string; title: string; desc: string;
               dotTone: ActivityItem['dotTone']; iconTone: ActivityItem['iconTone'];
               glyph: ActivityItem['glyph'] }
  const rows: Row[] = []

  for (const r of [...src.resumes].sort((a, b) =>
    String(b.uploaded_at).localeCompare(String(a.uploaded_at))).slice(0, 2)) {
    rows.push({
      at: String(r.uploaded_at || ''),
      title: '你上传了新的简历',
      desc: r.parse_status === 'ok'
        ? `已解析：${r.original_filename}`
        : r.parse_status === 'failed'
          ? `解析失败：${r.original_filename}`
          : `正在解析：${r.original_filename}`,
      dotTone: 'blue',
      iconTone: 'blue',
      glyph: 'file',
    })
  }

  if (src.profile) {
    rows.push({
      at: String(src.profile.created_at || ''),
      title: src.profile.confirmed ? '确认了能力画像' : '生成了能力画像',
      desc: `画像版本 v${src.profile.profile_version}${src.profile.confirmed ? '（已确认）' : '（待确认）'}`,
      dotTone: 'violet',
      iconTone: 'purple',
      glyph: 'briefcase',
    })
  }

  for (const run of [...src.runs].sort((a, b) =>
    String(b.created_at).localeCompare(String(a.created_at))).slice(0, 2)) {
    const h = mapRunToHistory(run)
    rows.push({
      at: String(run.created_at || ''),
      title: `发起了岗位推荐（${h.mode}）`,
      desc: `参与匹配岗位 ${h.jobCount} 个 · ${h.profileVersion}`,
      dotTone: 'green',
      iconTone: 'green',
      glyph: 'star',
    })
  }

  rows.sort((a, b) => String(b.at).localeCompare(String(a.at)))
  return rows.slice(0, 4).map((r, i, arr) => ({
    id: `${r.at}-${i}`,
    title: r.title,
    desc: r.desc,
    time: relativeTime(r.at),
    dotTone: r.dotTone,
    iconTone: r.iconTone,
    glyph: r.glyph,
    line: i < arr.length - 1,
  }))
}

// ---------------------------------------------------------------- 顶栏通知

export function buildNotifications(src: DashboardSource): NotificationItem[] {
  const out: NotificationItem[] = []
  if (src.resumes.length === 0) {
    out.push({ id: 'n-upload', text: '先上传简历即可生成能力画像' })
  }
  if (src.profile && !src.profile.confirmed) {
    out.push({ id: 'n-confirm', text: '当前画像待你确认后才会用于推荐' })
  }
  if (src.runTotal > 0) {
    out.push({ id: 'n-reco', text: `已为你累计生成 ${src.runTotal} 次岗位推荐` })
  }
  if (src.jobTotal > 0) {
    out.push({ id: 'n-jobs', text: `岗位库现有 ${src.jobTotal} 个已发布岗位` })
  }
  if (!out.length) {
    out.push({ id: 'n-empty', text: '暂无新通知' })
  }
  return out.slice(0, 3)
}

// ---------------------------------------------------------------- 汇总

export interface DashboardSummary {
  greeting: string
  lines: string[]
  studentName: string
  studentMeta: string
  statCards: StatCardItem[]
  progressSteps: ProgressStep[]
  progressStatus: ProgressStatus
  activityItems: ActivityItem[]
  notifications: NotificationItem[]
  /** 数据源不可用 / 来源未实现的说明（真实登记） */
  dataNotes: string[]
}

function greetingOf(d = new Date()): string {
  const h = d.getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '上午好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
}

export function buildSummary(src: DashboardSource, username: string): DashboardSummary {
  const major = src.profile
    ? String((src.profile.profile_data?.profile?.major as { value?: unknown } | undefined)?.value ?? '')
    : ''
  const education = src.profile
    ? String((src.profile.profile_data?.profile?.education_level as { value?: unknown } | undefined)?.value ?? '')
    : ''

  return {
    greeting: `${greetingOf()}，${username || '同学'}`,
    lines: [
      '新的一天，从探索更适合你的职业机会开始！',
      src.profile
        ? `当前画像版本 v${src.profile.profile_version}，推荐结果将基于该版本计算。`
        : '上传简历后，系统会基于你的画像准备岗位推荐。',
    ],
    studentName: username || '同学',
    studentMeta: [major, education].filter(Boolean).join(' · ') || '尚未完善个人画像',
    statCards: buildStatCards(src),
    progressSteps: buildProgressSteps(src),
    progressStatus: buildProgressStatus(src),
    activityItems: buildActivityItems(src),
    notifications: buildNotifications(src),
    dataNotes: src.notes,
  }
}
