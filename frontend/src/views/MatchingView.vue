<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import { listJobs } from '@/api/jobs'
import { mapRecoToMatchItem } from '@/api/mappers'
import { createRecommendation, getRun, listRuns } from '@/api/recommendations'
import type { JobRow, RecoItem } from '@/api/types'
import { useToast } from '@/composables/useToast'
import {
  categoryOptions,
  cityOptions,
  heroCopy,
  matchModes,
  profileOptions,
  topKOptions,
} from '@/data/matching'
import type {
  MatchCategoryStat,
  MatchDistributionSlice,
  MatchJobItem,
  MatchMode,
  MatchOverview,
} from '@/types/matching'

import bookmarkIcon from '@/assets/icons/match/bookmark-star.png'
import resetIcon from '@/assets/icons/action/reset-filter.png'
import startMatchIcon from '@/assets/icons/match/start-match.png'
import educationIcon from '@/assets/icons/match/education-match.png'
import intentIcon from '@/assets/icons/match/intent-aligned.png'
import projectIcon from '@/assets/icons/match/project-relevance.png'
import skillIcon from '@/assets/icons/match/skill-coverage.png'

const reasonIcons = {
  skill: skillIcon,
  education: educationIcon,
  project: projectIcon,
  intent: intentIcon,
}

const router = useRouter()
const { show } = useToast()

const profile = ref('v2')
const mode = ref<MatchMode>('综合排序')
const topK = ref('10')
const city = ref('all')
const category = ref('all')
const bookmarks = ref<Array<number | string>>([])
const running = ref(false)
const runCount = ref(0)

// 联调：推荐结果来自业务 API（baseline 打分 + 解释快照）
const matchJobs = ref<MatchJobItem[]>([])
const recoItems = ref<RecoItem[]>([])
const jobsMap = ref<Map<string, JobRow>>(new Map())
const currentRunId = ref('')
const loaded = ref(false)

/** 打分参考说明（后端 score 为排序参考分，不是录用概率） */
const noticeText =
  '匹配度与四维评分来自后端匹配服务的排序参考分（heuristic_score），仅用于岗位排序与求职参考，不代表企业录用概率。'

async function loadJobsMap() {
  const rows = await listJobs()
  jobsMap.value = new Map(rows.map((row) => [row.id, row]))
}

function applyRunItems(runId: string, items: RecoItem[]) {
  currentRunId.value = runId
  recoItems.value = items
  matchJobs.value = items.map((item) => mapRecoToMatchItem(item, jobsMap.value.get(item.job_id)))
}

async function loadLatestRun() {
  await loadJobsMap()
  const page = await listRuns(1, 1)
  const latest = page.items[0]
  if (!latest) return
  const run = await getRun(latest.id)
  applyRunItems(run.id, run.items || [])
}

onMounted(async () => {
  try {
    await loadLatestRun()
  } catch (e) {
    show(e instanceof Error ? e.message : '推荐记录加载失败')
  } finally {
    loaded.value = true
  }
})

const visibleJobs = computed(() => {
  let list = [...matchJobs.value]
  if (category.value !== 'all') {
    list = list.filter((job) => job.category === category.value)
  }
  if (mode.value === '高匹配优先') {
    list.sort((a, b) => b.match - a.match)
  } else if (mode.value === '高潜力优先') {
    list.sort((a, b) => b.potential - a.potential)
  }
  return list.slice(0, Number(topK.value))
})

const displayedAvg = computed(() => {
  const list = visibleJobs.value
  if (list.length === 0) return 0
  return Math.round(list.reduce((sum, job) => sum + job.match, 0) / list.length)
})

/** 概览统计由真实推荐项计算 */
const matchOverview = computed<MatchOverview>(() => {
  const items = recoItems.value
  const covered = new Set<string>()
  const missing = new Set<string>()
  for (const item of items) {
    for (const s of item.explanation_snapshot?.matched_skills ?? []) covered.add(String(s))
    for (const s of item.explanation_snapshot?.missing_required_skills ?? []) missing.add(String(s))
  }
  return {
    avgMatch: displayedAvg.value,
    highMatchCount: items.filter((i) => i.score * 100 >= 85).length,
    coveredSkills: covered.size,
    totalSkills: covered.size + missing.size,
  }
})

/** 匹配度分段分布（环形图） */
const distribution = computed<MatchDistributionSlice[]>(() => {
  const scores = recoItems.value.map((i) => i.score * 100)
  return [
    { label: '高匹配 85%+', value: scores.filter((s) => s >= 85).length, color: '#2168ff' },
    { label: '中匹配 70-84%', value: scores.filter((s) => s >= 70 && s < 85).length, color: '#03b58c' },
    { label: '待观察 <70%', value: scores.filter((s) => s < 70).length, color: '#ffb020' },
  ]
})

/** 岗位类别分布 */
const categoryStats = computed<MatchCategoryStat[]>(() => {
  const counts = new Map<string, number>()
  for (const job of matchJobs.value) {
    counts.set(job.industry, (counts.get(job.industry) || 0) + 1)
  }
  return [...counts.entries()].map(([label, value]) => ({ label, value }))
})

function isBookmarked(id: number | string) {
  return bookmarks.value.includes(id)
}

function toggleBookmark(job: MatchJobItem) {
  if (isBookmarked(job.id)) {
    bookmarks.value = bookmarks.value.filter((i) => i !== job.id)
    show(`已取消收藏「${job.title}」`)
  } else {
    bookmarks.value = [...bookmarks.value, job.id]
    show(`已收藏「${job.title}」`)
  }
}

async function handleStart() {
  if (running.value) return
  running.value = true
  show('正在调用匹配服务重新计算…', 'top')
  try {
    const result = await createRecommendation({
      mode: 'baseline',
      topK: Number(topK.value),
    })
    const run = await getRun(result.run.id)
    applyRunItems(run.id, run.items || [])
    runCount.value += 1
    show(`匹配完成，共为你找到 ${matchJobs.value.length} 个岗位`)
  } catch (e) {
    show(e instanceof Error ? e.message : '匹配执行失败')
  } finally {
    running.value = false
  }
}

function handleReset() {
  profile.value = 'v2'
  mode.value = '综合排序'
  topK.value = '10'
  city.value = 'all'
  category.value = 'all'
  show('匹配参数已重置')
}

function handleViewDetail(job: MatchJobItem) {
  router.push(`/job/${job.id}`)
}

const donutSlices = computed(() => {
  const slices = distribution.value
  const total = slices.reduce((sum, s) => sum + s.value, 0) || 1
  const circumference = 2 * Math.PI * 46
  let accumulated = 0
  return slices.map((slice) => {
    const length = (slice.value / total) * circumference
    const offset = -accumulated
    accumulated += length
    return { label: slice.label, color: slice.color, dash: `${length} ${circumference - length}`, offset }
  })
})

function ringDash(score: number) {
  const circumference = 2 * Math.PI * 26
  return `${(score / 100) * circumference} ${circumference}`
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <SideNav active-key="matching" />

    <main class="workspace">
      <section class="hero">
        <div class="hero-content">
          <h1>{{ heroCopy.title }}</h1>
          <p v-for="(line, i) in heroCopy.lines" :key="i">{{ line }}</p>
        </div>
      </section>

      <section class="panel settings-panel">
        <h2 class="panel-title">匹配设置</h2>
        <div class="setting-row">
          <div class="setting-item">
            <span class="setting-label">画像版本</span>
            <select v-model="profile" class="select-shell">
              <option v-for="opt in profileOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="setting-item">
            <span class="setting-label">匹配模式</span>
            <div class="mode-tabs">
              <button
                v-for="m in matchModes"
                :key="m"
                type="button"
                class="mode-tab"
                :class="{ active: mode === m }"
                @click="mode = m"
              >
                {{ m }}
              </button>
            </div>
          </div>
          <div class="setting-item">
            <span class="setting-label">推荐数量</span>
            <select v-model="topK" class="select-shell">
              <option v-for="opt in topKOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="setting-item">
            <span class="setting-label">城市</span>
            <select v-model="city" class="select-shell">
              <option v-for="opt in cityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="setting-item">
            <span class="setting-label">岗位类别</span>
            <select v-model="category" class="select-shell">
              <option v-for="opt in categoryOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="setting-actions">
            <button type="button" class="btn-primary" :disabled="running" @click="handleStart">
              <img class="btn-icon" :src="startMatchIcon" alt="" aria-hidden="true" />
              {{ running ? '匹配中…' : '开始匹配' }}
            </button>
            <button type="button" class="btn-ghost" @click="handleReset">
              <img class="btn-icon" :src="resetIcon" alt="" aria-hidden="true" />
              重置参数
            </button>
          </div>
        </div>
      </section>

      <div class="content-grid">
        <section class="panel result-panel">
          <div class="panel-head">
            <h2 class="panel-title">匹配结果</h2>
            <span class="panel-note">共 {{ visibleJobs.length }} 个岗位 · 平均匹配度 {{ displayedAvg }}%</span>
          </div>

          <article v-for="(job, index) in visibleJobs" :key="job.id" class="match-card">
            <div class="rank-badge" :class="{ top3: index < 3 }">NO.{{ index + 1 }}</div>
            <div class="match-card-main">
              <div class="job-head">
                <img class="job-logo" :src="job.logo" :alt="job.logoAlt" />
                <div class="job-head-text">
                  <h3>{{ job.title }}</h3>
                  <div class="job-company">{{ job.company }} <i /> {{ job.industry }} <i /> {{ job.location }}</div>
                </div>
                <div class="job-salary">{{ job.salary }} · {{ job.months }}薪</div>
              </div>

              <div class="reason-grid">
                <div v-for="reason in job.reasons" :key="reason.key" class="reason-item">
                  <div class="reason-label">
                    <img class="reason-icon" :src="reasonIcons[reason.key]" alt="" aria-hidden="true" />
                    {{ reason.label }}
                  </div>
                  <div class="reason-bar">
                    <span class="reason-fill" :style="{ width: reason.score + '%' }" />
                  </div>
                  <div class="reason-score">{{ reason.score }}%</div>
                </div>
              </div>

              <div class="job-tags">
                <span v-for="tag in job.tags" :key="tag" class="tag">{{ tag }}</span>
              </div>
              <div class="missing">
                <span class="missing-label">待补充技能</span>
                <span v-for="skill in job.missingSkills" :key="skill" class="missing-chip">{{ skill }}</span>
              </div>
            </div>

            <div class="match-card-side">
              <div class="ring-wrap">
                <svg viewBox="0 0 60 60" class="ring">
                  <circle cx="30" cy="30" r="26" class="ring-track" />
                  <circle
                    cx="30"
                    cy="30"
                    r="26"
                    class="ring-value"
                    :style="{ strokeDasharray: ringDash(job.match) }"
                  />
                </svg>
                <div class="ring-text">
                  <strong>{{ job.match }}%</strong>
                  <span>匹配度</span>
                </div>
              </div>
              <div class="side-actions">
                <button type="button" class="btn-outline" @click="handleViewDetail(job)">查看详情</button>
                <button
                  type="button"
                  class="btn-bookmark"
                  :class="{ active: isBookmarked(job.id) }"
                  @click="toggleBookmark(job)"
                >
                  <img class="btn-icon" :src="bookmarkIcon" alt="" aria-hidden="true" />
                  {{ isBookmarked(job.id) ? '已收藏' : '收藏' }}
                </button>
              </div>
            </div>
          </article>

          <p v-if="visibleJobs.length === 0" class="empty-tip">当前筛选条件下暂无匹配岗位，请调整参数后重新匹配。</p>
        </section>

        <aside class="side-column">
          <section class="panel">
            <h2 class="panel-title">匹配概览</h2>
            <div class="overview-grid">
              <div class="overview-item">
                <strong>{{ displayedAvg || matchOverview.avgMatch }}%</strong>
                <span>平均匹配度</span>
              </div>
              <div class="overview-item">
                <strong>{{ matchOverview.highMatchCount }}</strong>
                <span>高匹配岗位</span>
              </div>
              <div class="overview-item">
                <strong>{{ matchOverview.coveredSkills }}/{{ matchOverview.totalSkills }}</strong>
                <span>技能覆盖</span>
              </div>
            </div>
          </section>

          <section class="panel">
            <h2 class="panel-title">结果分布</h2>
            <div class="donut-wrap">
              <svg viewBox="0 0 120 120" class="donut">
                <circle
                  v-for="slice in donutSlices"
                  :key="slice.label"
                  cx="60"
                  cy="60"
                  r="46"
                  fill="none"
                  :stroke="slice.color"
                  stroke-width="16"
                  :stroke-dasharray="slice.dash"
                  :stroke-dashoffset="slice.offset"
                />
                <text x="60" y="57" text-anchor="middle" class="donut-total">{{ visibleJobs.length }}</text>
                <text x="60" y="74" text-anchor="middle" class="donut-sub">岗位数</text>
              </svg>
              <ul class="legend">
                <li v-for="slice in distribution" :key="slice.label">
                  <i :style="{ background: slice.color }" />
                  {{ slice.label }}
                </li>
              </ul>
            </div>
          </section>

          <section class="panel">
            <h2 class="panel-title">TOP5 岗位类别</h2>
            <div v-for="item in categoryStats" :key="item.label" class="bar-row">
              <span class="bar-label">{{ item.label }}</span>
              <div class="bar-track">
                <span class="bar-fill" :style="{ width: (item.value / 3) * 100 + '%' }" />
              </div>
              <span class="bar-value">{{ item.value }}</span>
            </div>
          </section>

          <section class="panel notice-panel">
            <h2 class="panel-title">重要提示</h2>
            <p>{{ noticeText }}</p>
          </section>
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

.panel {
  background: white;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 4px 14px rgba(45, 78, 139, 0.045);
}
.panel-title {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 800;
  color: #16234a;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.panel-head .panel-title {
  margin-bottom: 0;
}
.panel-note {
  font-size: 12px;
  color: #7b8aa9;
}

.settings-panel {
  margin-bottom: 12px;
}
.setting-row {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  flex-wrap: wrap;
}
.setting-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.setting-label {
  font-size: 12px;
  font-weight: 700;
  color: #4b5a7c;
}
.select-shell {
  height: 38px;
  min-width: 150px;
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  padding: 0 10px;
  font-size: 12px;
  color: #4b5a7c;
  background: white;
}
.mode-tabs {
  display: flex;
  height: 38px;
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  overflow: hidden;
}
.mode-tab {
  border: 0;
  background: white;
  padding: 0 14px;
  font-size: 12px;
  color: #4b5a7c;
}
.mode-tab + .mode-tab {
  border-left: 1px solid #e6edf7;
}
.mode-tab.active {
  background: #2168ff;
  color: white;
  font-weight: 700;
}
.setting-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 22px;
  background: #2168ff;
  color: white;
  border: 0;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
}
.btn-primary:hover {
  background: #1557e0;
}
.btn-primary:disabled {
  background: #8fb0f5;
}
.btn-ghost {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 18px;
  background: white;
  color: #4b5a7c;
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
}
.btn-icon {
  width: 15px;
  height: 15px;
  object-fit: contain;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 12px;
  align-items: start;
}
.side-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.match-card {
  display: flex;
  gap: 16px;
  border: 1px solid #e8eef7;
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 12px;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.match-card:hover {
  border-color: #b9d2ff;
  box-shadow: 0 6px 18px rgba(45, 78, 139, 0.08);
}
.rank-badge {
  align-self: flex-start;
  background: #f2f5fa;
  color: #8592ab;
  font-size: 11px;
  font-weight: 800;
  border-radius: 6px;
  padding: 5px 9px;
  flex-shrink: 0;
}
.rank-badge.top3 {
  background: #fff3e3;
  color: #ff8a1a;
}
.match-card-main {
  flex: 1;
  min-width: 0;
}
.job-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.job-logo {
  width: 46px;
  height: 46px;
  object-fit: contain;
  flex-shrink: 0;
}
.job-head-text {
  flex: 1;
  min-width: 0;
}
.job-head-text h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
  color: #16234a;
}
.job-company {
  font-size: 12px;
  color: #7b8aa9;
  margin-top: 5px;
}
.job-company i {
  display: inline-block;
  width: 1px;
  height: 10px;
  background: #d5deeb;
  margin: 0 8px;
  vertical-align: middle;
}
.job-salary {
  font-size: 17px;
  font-weight: 800;
  color: #ff6b1a;
  white-space: nowrap;
}
.reason-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 18px;
  margin: 12px 0;
}
.reason-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.reason-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #4b5a7c;
  white-space: nowrap;
}
.reason-icon {
  width: 14px;
  height: 14px;
  object-fit: contain;
}
.reason-bar {
  flex: 1;
  height: 6px;
  background: #eef2f8;
  border-radius: 3px;
  overflow: hidden;
}
.reason-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #4d8bff, #2168ff);
  border-radius: 3px;
}
.reason-score {
  font-size: 11px;
  font-weight: 700;
  color: #2168ff;
  width: 34px;
  text-align: right;
}
.job-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.tag {
  background: #f2f5fa;
  color: #6b7a99;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
}
.missing {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.missing-label {
  font-size: 11px;
  color: #8592ab;
}
.missing-chip {
  background: #fff4ec;
  color: #e2711d;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
}
.match-card-side {
  width: 180px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  justify-content: center;
}
.ring-wrap {
  position: relative;
  width: 84px;
  height: 84px;
}
.ring {
  width: 84px;
  height: 84px;
  transform: rotate(-90deg);
}
.ring-track {
  fill: none;
  stroke: #eef2f8;
  stroke-width: 7;
}
.ring-value {
  fill: none;
  stroke: #2168ff;
  stroke-width: 7;
  stroke-linecap: round;
}
.ring-text {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.ring-text strong {
  font-size: 17px;
  color: #2168ff;
}
.ring-text span {
  font-size: 10px;
  color: #8592ab;
}
.side-actions {
  display: flex;
  gap: 8px;
}
.btn-outline {
  border: 1px solid #2168ff;
  background: white;
  color: #2168ff;
  border-radius: 6px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 700;
}
.btn-bookmark {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid #d9e2ef;
  background: white;
  color: #4b5a7c;
  border-radius: 6px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 700;
}
.btn-bookmark.active {
  background: #e8f1ff;
  border-color: #2168ff;
  color: #2168ff;
}
.empty-tip {
  text-align: center;
  color: #8592ab;
  font-size: 13px;
  padding: 30px 0;
}

.overview-grid {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.overview-item {
  flex: 1;
  text-align: center;
}
.overview-item strong {
  display: block;
  font-size: 20px;
  color: #2168ff;
}
.overview-item span {
  font-size: 11px;
  color: #8592ab;
}
.donut-wrap {
  display: flex;
  align-items: center;
  gap: 14px;
}
.donut {
  width: 118px;
  height: 118px;
  transform: rotate(-90deg);
  flex-shrink: 0;
}
.donut-total,
.donut-sub {
  transform: rotate(90deg);
  transform-origin: center;
}
.donut-total {
  font-size: 22px;
  font-weight: 800;
  fill: #16234a;
}
.donut-sub {
  font-size: 10px;
  fill: #8592ab;
}
.legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.legend li {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: #4b5a7c;
}
.legend i {
  width: 9px;
  height: 9px;
  border-radius: 3px;
  flex-shrink: 0;
}
.bar-row {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 10px;
}
.bar-label {
  width: 68px;
  font-size: 11px;
  color: #4b5a7c;
  flex-shrink: 0;
}
.bar-track {
  flex: 1;
  height: 8px;
  background: #eef2f8;
  border-radius: 4px;
  overflow: hidden;
}
.bar-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #6ea3ff, #2168ff);
  border-radius: 4px;
}
.bar-value {
  font-size: 11px;
  font-weight: 700;
  color: #2168ff;
  width: 16px;
  text-align: right;
}
.notice-panel p {
  margin: 0;
  font-size: 11px;
  line-height: 1.8;
  color: #8592ab;
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
}
@media (max-width: 540px) {
  .workspace {
    margin-left: 0;
    padding: 70px 10px 82px;
  }
  .match-card {
    flex-direction: column;
  }
  .match-card-side {
    width: 100%;
    flex-direction: row;
    justify-content: space-between;
  }
  .reason-grid {
    grid-template-columns: 1fr;
  }
  .setting-actions {
    margin-left: 0;
    width: 100%;
  }
}
</style>
