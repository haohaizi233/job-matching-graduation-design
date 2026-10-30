<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import { listJobs } from '@/api/jobs'
import { dateTime, mapRecoToMatchItem } from '@/api/mappers'
import { createRecommendation, getRun, listRuns } from '@/api/recommendations'
import type { JobRow, RecoItem } from '@/api/types'
import { useToast } from '@/composables/useToast'
import {
  categoryOptions,
  cityOptions,
  distributionBands,
  heroCopy,
  matchModes,
  missingTipText,
  noticeLines,
  profileOptions,
  profileUpdateNote,
  topKOptions,
} from '@/data/matching'
import type {
  MatchCategoryStat,
  MatchDistributionSlice,
  MatchJobItem,
  MatchMode,
  MatchReason,
} from '@/types/matching'

import bannerArt from '@/assets/art/banner-campus-art.png'
import bookmarkIcon from '@/assets/icons/match/bookmark-star.png'
import startMatchIcon from '@/assets/icons/match/start-match.png'
import profileVersionIcon from '@/assets/icons/match/profile-version.png'
import educationIcon from '@/assets/icons/match/education-match.png'
import intentIcon from '@/assets/icons/match/intent-aligned.png'
import projectIcon from '@/assets/icons/match/project-relevance.png'
import skillIcon from '@/assets/icons/match/skill-coverage.png'
import skillAddIcon from '@/assets/icons/common/skill-add-orange.png'
import megaphoneIcon from '@/assets/icons/common/megaphone-orange.png'
import checkCircleIcon from '@/assets/icons/common/check-circle-mint.png'
import locationIcon from '@/assets/icons/job/location.png'

const reasonIcons = {
  skill: skillIcon,
  education: educationIcon,
  project: projectIcon,
  intent: intentIcon,
}

const router = useRouter()
const { show } = useToast()

const profile = ref(profileOptions[0]?.value ?? 'v2.3')
const mode = ref<MatchMode>('综合推荐')
const topK = ref('20')
const city = ref('')
const category = ref('')
const bookmarks = ref<Array<number | string>>([])
const running = ref(false)
const showDetails = ref(false)

// 联调：推荐结果来自业务 API（baseline 打分 + 解释快照）
const matchJobs = ref<MatchJobItem[]>([])
const recoItems = ref<RecoItem[]>([])
const jobsMap = ref<Map<string, JobRow>>(new Map())
const runMeta = ref<{ profileVersion: string; modelVersion: string; createdAt: string }>({
  profileVersion: '—',
  modelVersion: '—',
  createdAt: '—',
})
const loading = ref(true)
const loadError = ref('')

async function loadJobsMap() {
  const rows = await listJobs()
  jobsMap.value = new Map(rows.map((row) => [row.id, row]))
}

function applyRunItems(
  runId: string,
  items: RecoItem[],
  meta: { profileVersion: string; modelVersion: string; createdAt: string },
) {
  recoItems.value = items
  matchJobs.value = items.map((item) => mapRecoToMatchItem(item, jobsMap.value.get(item.job_id)))
  runMeta.value = meta
  void runId
}

async function loadLatestRun() {
  await loadJobsMap()
  const page = await listRuns(1, 1)
  const latest = page.items[0]
  if (!latest) return
  const run = await getRun(latest.id)
  applyRunItems(run.id, run.items || [], {
    profileVersion: run.profile_version != null ? `v${run.profile_version}` : '未生成画像',
    modelVersion: run.model_version || '—',
    createdAt: dateTime(run.created_at) || '—',
  })
}

onMounted(async () => {
  try {
    await loadLatestRun()
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : '推荐记录加载失败'
    show(loadError.value)
  } finally {
    loading.value = false
  }
})

const visibleJobs = computed(() => {
  let list = [...matchJobs.value]
  if (category.value) {
    list = list.filter((job) => job.category === category.value)
  }
  if (city.value) {
    list = list.filter((job) => job.location.includes(city.value))
  }
  if (mode.value === '高匹配优先') {
    list.sort((a, b) => b.match - a.match)
  } else if (mode.value === '高潜力优先') {
    list.sort((a, b) => b.potential - a.potential)
  }
  return list.slice(0, Number(topK.value))
})

/** 匹配结果分布（按当前展示的岗位分数段统计） */
const distribution = computed<MatchDistributionSlice[]>(() => {
  const scores = visibleJobs.value.map((job) => job.match)
  return distributionBands
    .map((band) => ({
      label: band.label,
      color: band.color,
      value: scores.filter((s) => s >= band.min && s < band.max).length,
    }))
    .filter((slice) => slice.value > 0)
})

/** TOP5 岗位类别（按行业标签聚合） */
const categoryStats = computed<MatchCategoryStat[]>(() => {
  const total = visibleJobs.value.length || 1
  const counts = new Map<string, number>()
  for (const job of visibleJobs.value) {
    counts.set(job.industry, (counts.get(job.industry) || 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([label, value]) => ({ label, value, percent: Math.round((value / total) * 100) }))
})

const filterSummary = computed(() => {
  const cityLabel = cityOptions.find((opt) => opt.value === city.value)?.label ?? '全部城市'
  const categoryLabel = categoryOptions.find((opt) => opt.value === category.value)?.label ?? '全部类别'
  return `${cityLabel} · ${categoryLabel}`
})

const donutSlices = computed(() => {
  const slices = distribution.value
  const total = slices.reduce((sum, s) => sum + s.value, 0) || 1
  const circumference = 2 * Math.PI * 46
  let accumulated = 0
  return slices.map((slice) => {
    const length = (slice.value / total) * circumference
    const offset = -accumulated
    accumulated += length
    return {
      label: slice.label,
      color: slice.color,
      dash: `${length} ${circumference - length}`,
      offset,
    }
  })
})

function ringDash(score: number) {
  const circumference = 2 * Math.PI * 34
  return `${(score / 100) * circumference} ${circumference}`
}

/** 匹配原因说明（由岗位画像与解释快照派生） */
function reasonDesc(job: MatchJobItem, key: MatchReason['key']): string {
  switch (key) {
    case 'skill': {
      const skills = job.tags.slice(0, 2).join('、')
      return skills ? `掌握 ${skills} 等核心技能，与岗位要求较为匹配` : '技能与岗位要求较为匹配'
    }
    case 'education':
      return `${job.education ?? '学历要求未标注'}，与简历学历基本符合`
    case 'project':
      return `项目方向贴近${job.industry}业务场景，具备相关实践`
    case 'intent':
      return `期望城市：${job.location}，岗位方向与求职意向较为一致`
    default:
      return ''
  }
}

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
    applyRunItems(run.id, run.items || [], {
      profileVersion: run.profile_version != null ? `v${run.profile_version}` : '未生成画像',
      modelVersion: run.model_version || '—',
      createdAt: dateTime(run.created_at) || '—',
    })
    show(`匹配完成，共为你找到 ${matchJobs.value.length} 个岗位`)
  } catch (e) {
    show(e instanceof Error ? e.message : '匹配执行失败')
  } finally {
    running.value = false
  }
}

function handleReset() {
  profile.value = profileOptions[0]?.value ?? 'v2.3'
  mode.value = '综合推荐'
  topK.value = '20'
  city.value = ''
  category.value = ''
  show('匹配参数已重置')
}

function handleViewDetail(job: MatchJobItem) {
  router.push(`/job/${job.id}`)
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <SideNav active-key="matching" />

    <main class="workspace">
      <section class="hero">
        <img class="hero-art" :src="bannerArt" alt="蓝天校园与纸飞机插画" />
        <div class="hero-copy">
          <h1>{{ heroCopy.title }}</h1>
          <p>{{ heroCopy.lead }}</p>
          <small>{{ heroCopy.sub }}</small>
        </div>
      </section>

      <section class="panel settings-panel">
        <div class="setting-heading">
          <h2>匹配设置</h2>
          <span>选择匹配参数，定制你的专属推荐结果</span>
        </div>
        <div class="setting-row">
          <div class="setting-field version-field">
            <label>选择画像版本 <i class="info-dot">i</i></label>
            <div class="version-select">
              <img class="version-icon" :src="profileVersionIcon" alt="" aria-hidden="true" />
              <select v-model="profile" aria-label="选择画像版本">
                <option v-for="opt in profileOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </div>
            <small>{{ profileUpdateNote }}</small>
          </div>

          <div class="setting-field strategy-field">
            <label>推荐模式 <i class="info-dot">i</i></label>
            <div class="strategy-options">
              <button
                v-for="m in matchModes"
                :key="m.key"
                type="button"
                class="strategy"
                :class="{ active: mode === m.key }"
                @click="mode = m.key"
              >
                <strong><span class="radio-dot" />{{ m.label }}</strong>
                <small>{{ m.desc }}</small>
              </button>
            </div>
          </div>

          <div class="setting-field">
            <label>推荐数量 Top K</label>
            <select v-model="topK" class="select-shell" aria-label="推荐数量 Top K">
              <option v-for="opt in topKOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>

          <div class="setting-field">
            <label>城市 <em>（可选）</em></label>
            <select v-model="city" class="select-shell" aria-label="城市">
              <option v-for="opt in cityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>

          <div class="setting-field">
            <label>岗位类别 <em>（可选）</em></label>
            <select v-model="category" class="select-shell" aria-label="岗位类别">
              <option v-for="opt in categoryOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>

          <button type="button" class="start-btn" :disabled="running" @click="handleStart">
            <img class="btn-icon" :src="startMatchIcon" alt="" aria-hidden="true" />
            {{ running ? '匹配中…' : '开始匹配' }}
          </button>
        </div>
      </section>

      <div class="columns">
        <section class="panel results-panel">
          <header class="results-heading">
            <div class="results-title">
              <h2>匹配结果</h2>
              <span>共为你找到 <b>{{ visibleJobs.length }}</b> 个匹配岗位</span>
            </div>
            <div class="score-note"><span class="warn-ico">!</span>匹配分仅用于排序参考，不代表录用概率</div>
          </header>

          <p v-if="loading" class="state-tip" role="status">正在加载推荐结果…</p>
          <p v-else-if="loadError" class="state-tip error" role="alert">
            {{ loadError }}
            <button type="button" class="text-btn" @click="loadLatestRun">重新加载</button>
          </p>
          <p v-else-if="visibleJobs.length === 0" class="state-tip">
            当前筛选条件下暂无匹配岗位，请调整参数后重新匹配。
          </p>

          <article v-for="(job, index) in visibleJobs" :key="job.id" class="job-card">
            <div class="rank-box" :class="{ gold: index === 0, silver: index === 1, bronze: index === 2 }">
              {{ index + 1 }}
            </div>
            <div class="job-body">
              <div class="job-top">
                <img class="job-logo" :src="job.logo" :alt="job.logoAlt" />
                <div class="job-head">
                  <h3>{{ job.title }}</h3>
                  <div class="job-company">{{ job.company }} <span class="company-chip">{{ job.industry }}</span></div>
                  <div class="job-meta">
                    <span><img class="meta-ico" :src="locationIcon" alt="" aria-hidden="true" />{{ job.location }}</span>
                    <span>{{ job.education }}</span>
                    <span class="salary-pill">{{ job.salary }}<template v-if="job.months"> · {{ job.months }}薪</template></span>
                  </div>
                  <div class="job-tags">
                    <span v-for="tag in job.tags" :key="tag" class="tag">{{ tag }}</span>
                  </div>
                </div>
                <div class="job-side">
                  <button
                    type="button"
                    class="star-btn"
                    :class="{ active: isBookmarked(job.id) }"
                    :aria-label="isBookmarked(job.id) ? '取消收藏' : '收藏岗位'"
                    @click="toggleBookmark(job)"
                  >
                    <img :src="bookmarkIcon" alt="" aria-hidden="true" />
                  </button>
                  <div class="ring-wrap">
                    <svg viewBox="0 0 84 84" class="ring">
                      <defs>
                        <linearGradient :id="`ring-grad-${index}`" x1="0" y1="0" x2="1" y2="1">
                          <stop offset="0%" stop-color="#3f7bff" />
                          <stop offset="100%" stop-color="#8b5cff" />
                        </linearGradient>
                      </defs>
                      <circle cx="42" cy="42" r="34" class="ring-track" />
                      <circle
                        cx="42"
                        cy="42"
                        r="34"
                        class="ring-value"
                        :stroke="`url(#ring-grad-${index})`"
                        :style="{ strokeDasharray: ringDash(job.match) }"
                      />
                    </svg>
                    <div class="ring-text">
                      <strong>{{ job.match }}%</strong>
                      <span>匹配度</span>
                    </div>
                  </div>
                  <button type="button" class="btn-detail" @click="handleViewDetail(job)">查看详情</button>
                </div>
              </div>

              <div class="reasons">
                <div class="reasons-label">匹配原因</div>
                <div class="reason-grid">
                  <div v-for="reason in job.reasons" :key="reason.key" class="reason-item">
                    <div class="reason-head">
                      <img class="reason-icon" :src="reasonIcons[reason.key]" alt="" aria-hidden="true" />
                      <span>{{ reason.label }}</span>
                      <b>{{ reason.score }}%</b>
                    </div>
                    <p>{{ reasonDesc(job, reason.key) }}</p>
                  </div>
                </div>
              </div>

              <div v-if="job.missingSkills.length" class="missing-strip">
                <div class="missing-row">
                  <img class="missing-ico" :src="skillAddIcon" alt="" aria-hidden="true" />
                  <span class="missing-label">待补充技能</span>
                  <span v-for="skill in job.missingSkills" :key="skill" class="missing-chip">{{ skill }}</span>
                </div>
                <p class="missing-tip">{{ missingTipText }}</p>
              </div>
            </div>
          </article>
        </section>

        <aside class="rightbar">
          <section class="panel overview">
            <header class="right-heading">
              <h2>匹配概览</h2>
              <button type="button" class="text-btn" @click="handleReset">重新设置</button>
            </header>
            <dl>
              <div><dt>当前使用画像版本</dt><dd>{{ runMeta.profileVersion }}</dd></div>
              <div><dt>模型版本</dt><dd>{{ runMeta.modelVersion }}</dd></div>
              <div>
                <dt>是否发生降级</dt>
                <dd class="good">
                  <img class="tiny-ico" :src="checkCircleIcon" alt="" aria-hidden="true" />否
                </dd>
              </div>
              <div><dt>推荐生成时间</dt><dd>{{ runMeta.createdAt }}</dd></div>
              <div><dt>本次推荐数量</dt><dd>{{ visibleJobs.length }} 个岗位</dd></div>
              <div><dt>筛选条件</dt><dd>{{ filterSummary }}</dd></div>
            </dl>
            <button type="button" class="details-toggle" @click="showDetails = !showDetails">
              查看详细参数
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ up: showDetails }">
                <path d="m8 9 4 4 4-4" />
              </svg>
            </button>
            <div v-if="showDetails" class="details-extra">
              <div>推荐策略：<span>{{ mode }}</span></div>
              <div>相似度及能力特征：多维加权</div>
              <div>推荐得分仅供参考</div>
            </div>
          </section>

          <section class="panel distribution">
            <h2>匹配结果分布</h2>
            <div class="dist-layout">
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
                </svg>
                <div class="donut-center">
                  <strong>{{ visibleJobs.length }}</strong>
                  <span>推荐岗位</span>
                </div>
              </div>
              <ul class="dist-legend">
                <li v-for="slice in distribution" :key="slice.label">
                  <i class="legend-dot" :style="{ background: slice.color }" />
                  {{ slice.label }}
                  <span>{{ slice.value }} ({{ Math.round((slice.value / (visibleJobs.length || 1)) * 100) }}%)</span>
                </li>
                <li v-if="distribution.length === 0" class="legend-empty">暂无匹配结果</li>
              </ul>
            </div>
            <div class="top-types">
              <h3>TOP 5 岗位类别</h3>
              <div v-for="item in categoryStats" :key="item.label" class="type-row">
                <span class="type-label">{{ item.label }}</span>
                <div class="type-track">
                  <span class="type-fill" :style="{ width: item.percent + '%' }" />
                </div>
                <span class="type-value">{{ item.value }} ({{ item.percent }}%)</span>
              </div>
            </div>
          </section>

          <section class="panel notice">
            <div class="notice-head">
              <img class="notice-ico" :src="megaphoneIcon" alt="" aria-hidden="true" />
              <strong>重要提示</strong>
            </div>
            <p v-for="(line, i) in noticeLines" :key="i">{{ line }}</p>
            <svg class="notice-doc" viewBox="0 0 60 70" aria-hidden="true">
              <path d="M8 2h31l15 14v49H8z" fill="#ffba85" />
              <path d="M39 2v14h15" fill="#fff0de" />
              <path d="M17 30h25M17 38h24M17 46h19" stroke="#fff4e9" stroke-width="4" stroke-linecap="round" />
            </svg>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}
.workspace {
  margin-left: 198px;
  padding: 75px 57px 35px 17px;
  background: linear-gradient(180deg, #f4f9ff 0%, #f8fbff 100%);
}

/* ---------- hero ---------- */
.hero {
  height: 138px;
  border-radius: 12px;
  position: relative;
  overflow: hidden;
  background: #dceaff;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 32px;
  margin-bottom: 12px;
}
.hero-art {
  position: absolute;
  right: 0;
  top: 0;
  height: 100%;
  width: 701px;
  object-fit: cover;
}
.hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(240, 250, 255, 0.96) 0%, rgba(231, 242, 255, 0.52) 42%, transparent 61%);
  pointer-events: none;
}
.hero-copy {
  position: relative;
  z-index: 1;
}
.hero-copy h1 {
  font-size: 27px;
  font-weight: 800;
  margin: 0 0 6px;
  letter-spacing: 0.5px;
  color: #0a1744;
}
.hero-copy p {
  font-size: 14px;
  line-height: 1.65;
  color: #233052;
  font-weight: 600;
  margin: 0;
}
.hero-copy small {
  display: block;
  font-size: 12px;
  color: #6a799b;
  line-height: 1.8;
}

/* ---------- 通用 ---------- */
.panel {
  background: white;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 4px 14px rgba(45, 78, 139, 0.045);
}
.panel h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 800;
  color: #16234a;
}
.text-btn {
  border: 0;
  background: none;
  color: #2168ff;
  font-size: 12px;
  font-weight: 700;
  padding: 0;
}
.text-btn:hover {
  text-decoration: underline;
}
.state-tip {
  text-align: center;
  color: #8592ab;
  font-size: 13px;
  padding: 28px 0;
}
.state-tip.error {
  color: #e25060;
}

/* ---------- 匹配设置 ---------- */
.settings-panel {
  margin-bottom: 12px;
}
.setting-heading {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
.setting-heading span {
  font-size: 12px;
  color: #8592ab;
}
.setting-row {
  display: flex;
  gap: 18px;
  align-items: flex-end;
  flex-wrap: wrap;
}
.setting-field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.setting-field label {
  font-size: 12px;
  font-weight: 700;
  color: #4b5a7c;
}
.setting-field label em {
  font-style: normal;
  color: #a3aec2;
  font-weight: 400;
}
.setting-field small {
  font-size: 11px;
  color: #a3aec2;
}
.info-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  border: 1px solid #b9c4d8;
  border-radius: 50%;
  font-size: 9px;
  font-style: normal;
  color: #8592ab;
  vertical-align: middle;
  margin-left: 2px;
}
.version-field {
  min-width: 176px;
}
.version-select {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 42px;
  border: 1px solid #d9e2ef;
  border-radius: 8px;
  padding: 0 10px;
  background: white;
}
.version-icon {
  width: 20px;
  height: 20px;
  object-fit: contain;
  flex-shrink: 0;
}
.version-select select {
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  font-size: 13px;
  color: #243457;
  font-weight: 700;
}
.select-shell {
  height: 42px;
  min-width: 132px;
  border: 1px solid #d9e2ef;
  border-radius: 8px;
  padding: 0 11px;
  font-size: 13px;
  color: #243457;
  background: white;
}
.strategy-options {
  display: flex;
  gap: 10px;
}
.strategy {
  display: flex;
  flex-direction: column;
  gap: 5px;
  align-items: flex-start;
  border: 1px solid #dbe4f2;
  border-radius: 8px;
  padding: 9px 13px;
  background: white;
  text-align: left;
}
.strategy strong {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: #243457;
}
.strategy small {
  font-size: 11px;
  color: #8b98b2;
}
.strategy .radio-dot {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 1px solid #b9c4d8;
  background: white;
}
.strategy.active {
  border-color: #2168ff;
  background: #f0f6ff;
}
.strategy.active strong {
  color: #2168ff;
}
.strategy.active .radio-dot {
  border: 4px solid #2168ff;
}
.start-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 42px;
  padding: 0 26px;
  margin-left: auto;
  background: #2168ff;
  color: white;
  border: 0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 700;
}
.start-btn:hover {
  background: #1557e0;
}
.start-btn:disabled {
  background: #8fb0f5;
  cursor: not-allowed;
}
.btn-icon {
  width: 16px;
  height: 16px;
  object-fit: contain;
}

/* ---------- 主体两栏 ---------- */
.columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 262px;
  gap: 12px;
  align-items: start;
}
.rightbar {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.rightbar .panel {
  padding: 15px;
}

/* ---------- 匹配结果 ---------- */
.results-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.results-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.results-title span {
  font-size: 12px;
  color: #7b8aa9;
}
.results-title b {
  color: #2168ff;
  font-size: 15px;
}
.score-note {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #ff7a2f;
}
.warn-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #ff7a2f;
  color: white;
  font-size: 11px;
  font-weight: 800;
}

.job-card {
  display: flex;
  gap: 14px;
  border: 1px solid #e8eef7;
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 12px;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.job-card:hover {
  border-color: #b9d2ff;
  box-shadow: 0 6px 18px rgba(45, 78, 139, 0.08);
}
.rank-box {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e3e9f4;
  border-radius: 8px;
  font-size: 20px;
  font-weight: 800;
  color: #8592ab;
  background: #f7f9fd;
}
.rank-box.gold {
  color: #d98a1a;
  border-color: #f0ddb4;
  background: #fff8e9;
}
.rank-box.silver {
  color: #7d8ca6;
  border-color: #dde4ef;
  background: #f2f5fa;
}
.rank-box.bronze {
  color: #b07a4a;
  border-color: #ecd9c4;
  background: #fbf3ea;
}
.job-body {
  flex: 1;
  min-width: 0;
}
.job-top {
  display: flex;
  gap: 14px;
}
.job-logo {
  width: 52px;
  height: 52px;
  object-fit: contain;
  flex-shrink: 0;
  border: 1px solid #eef2f8;
  border-radius: 10px;
  padding: 5px;
  background: white;
}
.job-head {
  flex: 1;
  min-width: 0;
}
.job-head h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
  color: #16234a;
}
.job-company {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 5px;
  font-size: 13px;
  font-weight: 700;
  color: #4b5a7c;
}
.company-chip {
  background: #f2f5fa;
  color: #8592ab;
  font-size: 10px;
  font-weight: 400;
  border-radius: 4px;
  padding: 2px 7px;
}
.job-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 7px;
  font-size: 12px;
  color: #7b8aa9;
  flex-wrap: wrap;
}
.job-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.meta-ico {
  width: 13px;
  height: 13px;
  object-fit: contain;
}
.salary-pill {
  color: #ff6b1a;
  font-weight: 800;
}
.job-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 9px;
}
.tag {
  background: #f2f5fa;
  color: #6b7a99;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
}
.job-side {
  width: 150px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.star-btn {
  align-self: flex-end;
  padding: 0;
  line-height: 0;
}
.star-btn img {
  width: 19px;
  height: 19px;
  object-fit: contain;
  opacity: 0.75;
}
.star-btn.active img {
  opacity: 1;
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
  stroke-width: 8;
}
.ring-value {
  fill: none;
  stroke-width: 8;
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
  font-size: 18px;
  color: #4a5fd0;
}
.ring-text span {
  font-size: 10px;
  color: #8592ab;
}
.btn-detail {
  border: 1px solid #2168ff;
  background: white;
  color: #2168ff;
  border-radius: 6px;
  padding: 7px 16px;
  font-size: 12px;
  font-weight: 700;
}
.btn-detail:hover {
  background: #eef4ff;
}

/* 匹配原因 */
.reasons {
  display: flex;
  gap: 12px;
  margin-top: 14px;
}
.reasons-label {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 700;
  color: #4b5a7c;
  padding-top: 2px;
}
.reason-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.reason-item {
  min-width: 0;
}
.reason-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  color: #243457;
}
.reason-icon {
  width: 16px;
  height: 16px;
  object-fit: contain;
  flex-shrink: 0;
}
.reason-head b {
  color: #2168ff;
  font-size: 12px;
}
.reason-item p {
  margin: 6px 0 0;
  font-size: 11px;
  line-height: 1.7;
  color: #8592ab;
}

/* 待补充技能 */
.missing-strip {
  margin-top: 12px;
  background: #fff6ee;
  border: 1px solid #ffe3cd;
  border-radius: 8px;
  padding: 10px 12px;
}
.missing-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.missing-ico {
  width: 15px;
  height: 15px;
  object-fit: contain;
}
.missing-label {
  font-size: 12px;
  font-weight: 700;
  color: #d9691f;
}
.missing-chip {
  background: #ffe6d2;
  color: #c9601c;
  font-size: 10px;
  padding: 3px 9px;
  border-radius: 4px;
}
.missing-tip {
  margin: 7px 0 0;
  font-size: 11px;
  color: #b4703c;
  line-height: 1.7;
}

/* ---------- 匹配概览 ---------- */
.right-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.overview dl {
  margin: 0;
}
.overview dl > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px dashed #eef2f8;
}
.overview dt {
  font-size: 11px;
  color: #8592ab;
  white-space: nowrap;
}
.overview dd {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  color: #243457;
  text-align: right;
}
.overview dd.good {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #03b58c;
}
.tiny-ico {
  width: 13px;
  height: 13px;
  object-fit: contain;
}
.details-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  margin-top: 12px;
  border: 0;
  border-radius: 6px;
  background: #f2f7ff;
  color: #2168ff;
  font-size: 12px;
  font-weight: 700;
  padding: 8px 0;
}
.details-toggle svg {
  width: 13px;
  height: 13px;
  transition: transform 0.2s;
}
.details-toggle svg.up {
  transform: rotate(180deg);
}
.details-extra {
  margin-top: 10px;
  font-size: 11px;
  color: #7b8aa9;
  line-height: 2;
}

/* ---------- 匹配结果分布 ---------- */
.dist-layout {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0 4px;
}
.donut-wrap {
  position: relative;
  width: 116px;
  height: 116px;
  flex-shrink: 0;
}
.donut {
  width: 116px;
  height: 116px;
  transform: rotate(-90deg);
}
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.donut-center strong {
  font-size: 22px;
  color: #16234a;
}
.donut-center span {
  font-size: 10px;
  color: #8592ab;
}
.dist-legend {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dist-legend li {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: #4b5a7c;
}
.dist-legend li span {
  margin-left: auto;
  color: #243457;
  font-weight: 700;
}
.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}
.legend-empty {
  color: #a3aec2;
}
.top-types {
  margin-top: 14px;
}
.top-types h3 {
  margin: 0 0 10px;
  font-size: 12px;
  font-weight: 800;
  color: #16234a;
}
.type-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 9px;
}
.type-label {
  width: 88px;
  font-size: 11px;
  color: #4b5a7c;
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.type-track {
  flex: 1;
  height: 8px;
  background: #eef2f8;
  border-radius: 4px;
  overflow: hidden;
}
.type-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #6ea3ff, #2168ff);
  border-radius: 4px;
}
.type-value {
  font-size: 11px;
  font-weight: 700;
  color: #2168ff;
  white-space: nowrap;
}

/* ---------- 重要提示 ---------- */
.notice {
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #fff7ec 0%, #ffeed9 100%);
  border-color: #ffe0bd;
}
.notice-head {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 9px;
}
.notice-head strong {
  font-size: 13px;
  color: #d9691f;
}
.notice-ico {
  width: 17px;
  height: 17px;
  object-fit: contain;
}
.notice p {
  position: relative;
  z-index: 1;
  margin: 0 0 7px;
  font-size: 11px;
  line-height: 1.85;
  color: #a1613a;
}
.notice-doc {
  position: absolute;
  right: 10px;
  bottom: 8px;
  width: 52px;
  height: 60px;
  opacity: 0.9;
}

@media (max-width: 1380px) {
  .workspace {
    padding-right: 18px;
  }
}
@media (max-width: 1100px) {
  .workspace {
    margin-left: 76px;
    padding-top: 71px;
  }
  .columns {
    grid-template-columns: 1fr;
  }
  .setting-row {
    gap: 14px;
  }
  .strategy-options {
    flex-wrap: wrap;
  }
}
@media (max-width: 540px) {
  .workspace {
    margin-left: 0;
    padding: 70px 10px 82px;
  }
  .hero {
    height: 125px;
    padding: 0 15px;
  }
  .hero-copy h1 {
    font-size: 23px;
  }
  .hero-copy p {
    font-size: 12px;
  }
  .hero-copy small {
    font-size: 10px;
    max-width: 85%;
  }
  .job-card {
    flex-direction: column;
  }
  .job-top {
    flex-wrap: wrap;
  }
  .job-side {
    width: 100%;
    flex-direction: row;
    justify-content: space-between;
  }
  .reasons {
    flex-direction: column;
  }
  .reason-grid {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .start-btn {
    margin-left: 0;
    width: 100%;
    justify-content: center;
  }
}
</style>
