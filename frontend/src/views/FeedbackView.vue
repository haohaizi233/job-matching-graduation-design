<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import { listJobs } from '@/api/jobs'
import { mapFeedbackToRecord } from '@/api/mappers'
import { createRecommendation, getRun, listFeedback, listRuns, submitFeedback } from '@/api/recommendations'
import type { FeedbackRow, JobRow } from '@/api/types'
import { useToast } from '@/composables/useToast'
import {
  heroCopy,
  statusOptions,
  statusText,
  trendRanges,
} from '@/data/feedback'
import type { FeedbackRecordItem, FeedbackStatItem, FeedbackStatus } from '@/types/feedback'

import appliedIcon from '@/assets/icons/feedback/applied-job.png'
import interviewIcon from '@/assets/icons/feedback/interview-gained.png'
import thumbDownIcon from '@/assets/icons/feedback/thumb-down-red.png'
import thumbUpIcon from '@/assets/icons/feedback/thumb-up-blue.png'
import bookmarkIcon from '@/assets/icons/feedback/job-bookmark.png'
import againIcon from '@/assets/icons/status/recommend-again.png'
import statFeedbackIcon from '@/assets/icons/feedback/tile/today-feedback.png'
import statInterestedIcon from '@/assets/icons/feedback/tile/interested-job.png'
import statAppliedIcon from '@/assets/icons/feedback/tile/applied-job.png'
import statPendingIcon from '@/assets/icons/feedback/tile/pending-suggestion.png'

const { show } = useToast()

const statIcons = [statFeedbackIcon, statInterestedIcon, statAppliedIcon, statPendingIcon]
const actionButtons: { status: FeedbackStatus; label: string; icon: string }[] = [
  { status: 'interested', label: '感兴趣', icon: thumbUpIcon },
  { status: 'notInterested', label: '不感兴趣', icon: thumbDownIcon },
  { status: 'applied', label: '已投递', icon: appliedIcon },
  { status: 'interviewed', label: '已面试', icon: interviewIcon },
]

// 联调：反馈记录来自业务 API（推荐明细上的用户反馈）
const records = ref<FeedbackRecordItem[]>([])
const loading = ref(true)
/** 反馈 → 推荐上下文（提交新反馈需要 run_id + item_id；相似推荐需要 job_id） */
const feedbackMeta = ref<Map<number | string, { runId: string; itemId: string; jobId: string }>>(new Map())

const activeRange = ref('7d')
const activeStatus = ref<'all' | FeedbackStatus>('all')
const keyword = ref('')
const selectedId = ref<number | string>('')
const noteDraft = ref('')

onMounted(async () => {
  try {
    const [feedbackRows, jobRows, runsPage] = await Promise.all([
      listFeedback(),
      listJobs(),
      listRuns(1, 20),
    ])
    const jobsMap = new Map<string, JobRow>(jobRows.map((row) => [row.id, row]))

    // 推荐明细项 id → 岗位/运行上下文（后端反馈只存 item_id）
    const itemCtx = new Map<string, { runId: string; jobId: string }>()
    for (const run of runsPage.items) {
      const detail = await getRun(run.id)
      for (const item of detail.items || []) {
        itemCtx.set(item.id, { runId: run.id, jobId: item.job_id })
      }
    }

    const built: FeedbackRecordItem[] = []
    const meta = new Map<number | string, { runId: string; itemId: string; jobId: string }>()
    for (const fb of feedbackRows as FeedbackRow[]) {
      const ctx = itemCtx.get(fb.recommendation_item_id)
      const job = ctx ? jobsMap.get(ctx.jobId) ?? null : null
      built.push(mapFeedbackToRecord(fb, job))
      if (ctx) {
        meta.set(fb.id, { runId: ctx.runId, itemId: fb.recommendation_item_id, jobId: ctx.jobId })
      }
    }
    records.value = built
    feedbackMeta.value = meta
    selectedId.value = built[0]?.id ?? ''
  } catch (e) {
    show(e instanceof Error ? e.message : '反馈记录加载失败')
  } finally {
    loading.value = false
  }
})

/** 统计卡按真实反馈记录计算 */
const feedbackStats = computed<FeedbackStatItem[]>(() => {
  const list = records.value
  const count = (status: FeedbackStatus) => list.filter((r) => r.status === status).length
  return [
    { key: 'total', label: '反馈总数', value: String(list.length), note: '来自推荐明细' },
    { key: 'interested', label: '感兴趣', value: String(count('interested')), note: '愿意继续了解' },
    { key: 'applied', label: '已投递', value: String(count('applied')), note: '已向企业投递' },
    { key: 'interviewed', label: '已面试', value: String(count('interviewed')), note: '进入面试环节' },
  ]
})

const filteredRecords = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return records.value.filter((record) => {
    if (activeStatus.value !== 'all' && record.status !== activeStatus.value) return false
    if (kw && !`${record.title} ${record.company}`.toLowerCase().includes(kw)) return false
    return true
  })
})

const selectedRecord = computed(() => {
  return records.value.find((record) => record.id === selectedId.value)
})

const currentTrend = computed(() => {
  return trendRanges.find((range) => range.value === activeRange.value) ?? trendRanges[0]
})

const trendChart = computed(() => {
  const points = currentTrend.value.points
  const max = Math.max(...points.map((p) => p.value), 1)
  const width = 560
  const height = 180
  const paddingX = 36
  const paddingY = 22
  const stepX = points.length > 1 ? (width - paddingX * 2) / (points.length - 1) : 0
  const coords = points.map((point, index) => ({
    ...point,
    x: paddingX + index * stepX,
    y: height - paddingY - (point.value / max) * (height - paddingY * 2),
  }))
  const polyline = coords.map((c) => `${c.x},${c.y}`).join(' ')
  return { width, height, paddingX, paddingY, coords, polyline, max }
})

function handleSelect(record: FeedbackRecordItem) {
  selectedId.value = record.id
  noteDraft.value = record.note
}

async function handleStatusChange(status: FeedbackStatus) {
  const record = selectedRecord.value
  if (!record) return
  const meta = feedbackMeta.value.get(record.id)
  if (!meta) {
    show('该记录缺少推荐上下文，无法提交新反馈')
    return
  }
  try {
    await submitFeedback({
      runId: meta.runId,
      itemId: meta.itemId,
      feedbackType: status,
      note: record.note || undefined,
    })
    record.status = status
    record.bookmarked = status === 'interested'
    show(`已将「${record.title}」标记为${statusText[status]}`)
  } catch (e) {
    show(e instanceof Error ? e.message : '反馈提交失败')
  }
}

function handleSaveNote() {
  const record = selectedRecord.value
  if (!record) return
  record.note = noteDraft.value
  show('备注已本地保存（后端暂无备注更新接口）')
}

function handleToggleBookmark() {
  const record = selectedRecord.value
  if (!record) return
  record.bookmarked = !record.bookmarked
  show(record.bookmarked ? `已收藏「${record.title}」` : `已取消收藏「${record.title}」`)
}

function handleWithdraw() {
  const record = selectedRecord.value
  if (!record) return
  show('反馈撤回暂未开放（后端暂无撤回接口）')
}

async function handleRecommendAgain() {
  const record = selectedRecord.value
  if (!record) return
  const meta = feedbackMeta.value.get(record.id)
  show(`正在为你重新推荐与「${record.title}」相似的岗位…`)
  try {
    await createRecommendation({
      mode: 'baseline',
      jobIds: meta ? [meta.jobId] : undefined,
    })
    show('已生成新的推荐结果，可到智能匹配页查看')
  } catch (e) {
    show(e instanceof Error ? e.message : '重新推荐失败')
  }
}

function handleStatusFilter(value: typeof activeStatus.value) {
  activeStatus.value = value
}

function handleRangeChange(value: string) {
  activeRange.value = value
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <SideNav active-key="feedback" />

    <main class="workspace">
      <section class="hero">
        <div class="hero-content">
          <h1>{{ heroCopy.title }}</h1>
          <p v-for="(line, i) in heroCopy.lines" :key="i">{{ line }}</p>
        </div>
      </section>

      <section class="stats-grid" aria-label="反馈统计">
        <div v-for="(item, index) in feedbackStats" :key="item.key" class="stat-card">
          <img class="stat-icon" :src="statIcons[index]" alt="" aria-hidden="true" />
          <div class="stat-text">
            <span class="stat-label">{{ item.label }}</span>
            <strong class="stat-value">{{ item.value }}</strong>
            <span class="stat-note">{{ item.note }}</span>
          </div>
        </div>
      </section>

      <section class="panel trend-panel">
        <div class="panel-head">
          <h2 class="panel-title">反馈趋势</h2>
          <div class="range-tabs">
            <button
              v-for="range in trendRanges"
              :key="range.value"
              type="button"
              class="range-tab"
              :class="{ active: activeRange === range.value }"
              @click="handleRangeChange(range.value)"
            >
              {{ range.label }}
            </button>
          </div>
        </div>
        <svg
          class="trend-svg"
          :viewBox="`0 0 ${trendChart.width} ${trendChart.height}`"
          preserveAspectRatio="none"
          role="img"
          aria-label="反馈趋势折线图"
        >
          <line
            v-for="n in 4"
            :key="n"
            :x1="trendChart.paddingX"
            :x2="trendChart.width - trendChart.paddingX"
            :y1="trendChart.paddingY + ((n - 1) * (trendChart.height - trendChart.paddingY * 2)) / 3"
            :y2="trendChart.paddingY + ((n - 1) * (trendChart.height - trendChart.paddingY * 2)) / 3"
            class="grid-line"
          />
          <polyline :points="trendChart.polyline" class="trend-line" />
          <circle
            v-for="point in trendChart.coords"
            :key="point.label"
            :cx="point.x"
            :cy="point.y"
            r="4"
            class="trend-dot"
          />
          <text
            v-for="point in trendChart.coords"
            :key="`label-${point.label}`"
            :x="point.x"
            :y="trendChart.height - 6"
            text-anchor="middle"
            class="axis-label"
          >
            {{ point.label }}
          </text>
          <text
            v-for="point in trendChart.coords"
            :key="`value-${point.label}`"
            :x="point.x"
            :y="point.y - 10"
            text-anchor="middle"
            class="point-value"
          >
            {{ point.value }}
          </text>
        </svg>
      </section>

      <div class="content-grid">
        <section class="panel list-panel">
          <div class="panel-head">
            <h2 class="panel-title">反馈记录</h2>
            <div class="list-tools">
              <div class="filter-tabs">
                <button
                  v-for="opt in statusOptions"
                  :key="opt.value"
                  type="button"
                  class="filter-tab"
                  :class="{ active: activeStatus === opt.value }"
                  @click="handleStatusFilter(opt.value)"
                >
                  {{ opt.label }}
                </button>
              </div>
              <div class="search-shell">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>
                <input v-model="keyword" placeholder="搜索公司或岗位" />
              </div>
            </div>
          </div>

          <div class="record-table">
            <div class="table-head">
              <span>岗位</span>
              <span>反馈时间</span>
              <span>状态</span>
            </div>
            <button
              v-for="record in filteredRecords"
              :key="record.id"
              type="button"
              class="table-row"
              :class="{ active: selectedId === record.id }"
              @click="handleSelect(record)"
            >
              <div class="cell-job">
                <img class="job-logo" :src="record.logo" :alt="record.logoAlt" />
                <div>
                  <strong>{{ record.title }}</strong>
                  <span>{{ record.company }} · {{ record.industry }}</span>
                </div>
              </div>
              <span class="cell-time">{{ record.time }}</span>
              <span class="status-badge" :class="record.status">{{ statusText[record.status] }}</span>
            </button>
            <p v-if="filteredRecords.length === 0" class="empty-tip">没有符合条件的反馈记录。</p>
          </div>
        </section>

        <aside v-if="selectedRecord" class="panel detail-panel">
          <h2 class="panel-title">反馈详情</h2>
          <div class="detail-job">
            <img class="detail-logo" :src="selectedRecord.logo" :alt="selectedRecord.logoAlt" />
            <div>
              <strong>{{ selectedRecord.title }}</strong>
              <span>{{ selectedRecord.company }} · {{ selectedRecord.location }}</span>
            </div>
          </div>
          <div class="detail-meta">
            <span>{{ selectedRecord.salary }}</span>
            <span>{{ selectedRecord.time }}</span>
          </div>

          <h3 class="detail-subtitle">修改反馈状态</h3>
          <div class="status-actions">
            <button
              v-for="btn in actionButtons"
              :key="btn.status"
              type="button"
              class="status-btn"
              :class="{ active: selectedRecord.status === btn.status }"
              @click="handleStatusChange(btn.status)"
            >
              <img :src="btn.icon" alt="" aria-hidden="true" />
              {{ btn.label }}
            </button>
          </div>

          <h3 class="detail-subtitle">备注</h3>
          <textarea
            v-model="noteDraft"
            class="note-input"
            rows="3"
            placeholder="记录你的想法，例如：岗位方向符合预期…"
          />
          <button type="button" class="btn-primary full" @click="handleSaveNote">保存备注</button>

          <div class="detail-actions">
            <button type="button" class="btn-outline" @click="handleToggleBookmark">
              <img :src="bookmarkIcon" alt="" aria-hidden="true" />
              {{ selectedRecord.bookmarked ? '已收藏' : '收藏岗位' }}
            </button>
            <button type="button" class="btn-outline" @click="handleWithdraw">撤回反馈</button>
            <button type="button" class="btn-primary" @click="handleRecommendAgain">
              <img :src="againIcon" alt="" aria-hidden="true" />
              再次推荐
            </button>
          </div>
        </aside>
      </div>
    </main>
  </div>
</template>

<style scoped>
.hero {
  height: 138px;
  border-radius: 12px;
  background: linear-gradient(110deg, #eff7ff 0%, #daeaff 47%, #b8d8ff 75%, #c1d3ff 100%);
  margin-bottom: 12px;
  padding: 0 37px;
  display: flex;
  align-items: center;
}
.hero-content h1 {
  font-size: 30px;
  margin: 0 0 8px;
  font-weight: 800;
  letter-spacing: -1px;
  color: #101d46;
}
.hero-content p {
  margin: 0;
  line-height: 1.75;
  color: #41567f;
  font-size: 14px;
  font-weight: 500;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.stat-card {
  background: white;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  align-items: center;
  gap: 13px;
  box-shadow: 0 4px 14px rgba(45, 78, 139, 0.045);
}
.stat-icon {
  width: 42px;
  height: 42px;
  object-fit: contain;
  flex-shrink: 0;
}
.stat-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.stat-label {
  font-size: 11px;
  color: #8592ab;
}
.stat-value {
  font-size: 22px;
  font-weight: 800;
  color: #16234a;
  line-height: 1.1;
}
.stat-note {
  font-size: 10px;
  color: #03b58c;
}

.panel {
  background: white;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 4px 14px rgba(45, 78, 139, 0.045);
  margin-bottom: 12px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 800;
  color: #16234a;
}

.range-tabs {
  display: flex;
  gap: 8px;
}
.range-tab {
  border: 1px solid #dde5f0;
  background: #f7f9fc;
  color: #5b6b8d;
  border-radius: 14px;
  padding: 4px 12px;
  font-size: 11px;
}
.range-tab.active {
  background: #e3edff;
  border-color: #2168ff;
  color: #2168ff;
  font-weight: 700;
}
.trend-svg {
  width: 100%;
  height: 190px;
}
.grid-line {
  stroke: #eef2f8;
  stroke-width: 1;
}
.trend-line {
  fill: none;
  stroke: #2168ff;
  stroke-width: 2.5;
  stroke-linejoin: round;
}
.trend-dot {
  fill: white;
  stroke: #2168ff;
  stroke-width: 2.5;
}
.axis-label {
  font-size: 10px;
  fill: #8b98b2;
}
.point-value {
  font-size: 10px;
  font-weight: 700;
  fill: #2168ff;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 310px;
  gap: 12px;
  align-items: start;
}
.content-grid .panel {
  margin-bottom: 0;
}

.list-tools {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.filter-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.filter-tab {
  border: 1px solid #dde5f0;
  background: #f7f9fc;
  color: #5b6b8d;
  border-radius: 14px;
  padding: 4px 11px;
  font-size: 11px;
}
.filter-tab.active {
  background: #e3edff;
  border-color: #2168ff;
  color: #2168ff;
  font-weight: 700;
}
.search-shell {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  padding: 0 10px;
  color: #9ca8bf;
}
.search-shell svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}
.search-shell input {
  border: 0;
  outline: 0;
  font-size: 12px;
  color: #243457;
  width: 130px;
}

.record-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.table-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 130px 90px;
  gap: 12px;
  padding: 0 14px;
  font-size: 11px;
  color: #8b98b2;
}
.table-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 130px 90px;
  gap: 12px;
  align-items: center;
  border: 1px solid #e8eef7;
  border-radius: 8px;
  padding: 10px 14px;
  text-align: left;
  transition: border-color 0.2s, background 0.2s;
}
.table-row:hover {
  border-color: #b9d2ff;
}
.table-row.active {
  border-color: #2168ff;
  background: #f5f9ff;
}
.cell-job {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.cell-job strong {
  display: block;
  font-size: 13px;
  color: #16234a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cell-job span {
  font-size: 11px;
  color: #8592ab;
}
.job-logo {
  width: 34px;
  height: 34px;
  object-fit: contain;
  flex-shrink: 0;
}
.cell-time {
  font-size: 11px;
  color: #7b8aa9;
}
.status-badge {
  justify-self: start;
  font-size: 10px;
  padding: 3px 9px;
  border-radius: 4px;
  font-weight: 700;
  white-space: nowrap;
}
.status-badge.interested {
  background: #e8f1ff;
  color: #2168ff;
}
.status-badge.notInterested {
  background: #f2f4f8;
  color: #8b98b2;
}
.status-badge.applied {
  background: #e5f8f2;
  color: #03b58c;
}
.status-badge.interviewed {
  background: #fff3e3;
  color: #ff8a1a;
}
.status-badge.irrelevant {
  background: #ffeef0;
  color: #e25060;
}
.empty-tip {
  text-align: center;
  color: #8592ab;
  font-size: 13px;
  padding: 24px 0;
}

.detail-panel .panel-title {
  margin-bottom: 14px;
}
.detail-job {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 8px;
}
.detail-logo {
  width: 44px;
  height: 44px;
  object-fit: contain;
}
.detail-job strong {
  display: block;
  font-size: 14px;
  color: #16234a;
}
.detail-job span {
  font-size: 11px;
  color: #8592ab;
}
.detail-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #7b8aa9;
  margin-bottom: 14px;
}
.detail-meta span:first-child {
  color: #ff6b1a;
  font-weight: 800;
}
.detail-subtitle {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  color: #4b5a7c;
}
.status-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}
.status-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid #d9e2ef;
  background: white;
  color: #4b5a7c;
  border-radius: 6px;
  padding: 8px 6px;
  font-size: 12px;
  font-weight: 700;
}
.status-btn img {
  width: 15px;
  height: 15px;
  object-fit: contain;
}
.status-btn.active {
  background: #e8f1ff;
  border-color: #2168ff;
  color: #2168ff;
}
.note-input {
  width: 100%;
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  padding: 9px 11px;
  font-size: 12px;
  color: #243457;
  resize: vertical;
  outline: 0;
  box-sizing: border-box;
}
.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  background: #2168ff;
  color: white;
  border: 0;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
}
.btn-primary:hover {
  background: #1557e0;
}
.btn-primary.full {
  width: 100%;
  margin-top: 8px;
}
.btn-primary img,
.btn-outline img {
  width: 14px;
  height: 14px;
  object-fit: contain;
}
.btn-outline {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding: 0 13px;
  border: 1px solid #d9e2ef;
  background: white;
  color: #4b5a7c;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
}
.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

@media (max-width: 1190px) {
  .workspace {
    padding-right: 18px;
  }
}
@media (max-width: 1000px) {
  .workspace {
    margin-left: 76px;
  }
  .content-grid {
    grid-template-columns: 1fr;
  }
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 540px) {
  .workspace {
    margin-left: 0;
    padding: 70px 10px 82px;
  }
  .stats-grid {
    grid-template-columns: 1fr;
  }
  .table-head {
    display: none;
  }
  .table-row {
    grid-template-columns: 1fr;
    gap: 8px;
  }
}
</style>
