<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import ActivityCard from '@/components/dashboard/ActivityCard.vue'
import JobDetailDialog from '@/components/dashboard/JobDetailDialog.vue'
import JobProgressPanel from '@/components/dashboard/JobProgressPanel.vue'
import MatchPromo from '@/components/dashboard/MatchPromo.vue'
import NoticeCard from '@/components/dashboard/NoticeCard.vue'
import RecommendCard from '@/components/dashboard/RecommendCard.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import StatsGrid from '@/components/dashboard/StatsGrid.vue'
import TopBar from '@/components/dashboard/TopBar.vue'
import TrendCard from '@/components/dashboard/TrendCard.vue'
import WelcomeBanner from '@/components/dashboard/WelcomeBanner.vue'
import { useDashboardSummary } from '@/composables/useDashboardSummary'
import { useToast } from '@/composables/useToast'
import type { JobItem, StatCardItem } from '@/types'

/** 匹配分免责说明（固定文案，非业务数据） */
const NOTICE_TEXT =
  '系统提供的岗位匹配评分仅基于你的简历画像与岗位要求的相似度计算，用于排序和推荐参考，不代表企业的实际录用概率。请结合自身情况综合判断，并主动了解企业的招聘要求。'

const router = useRouter()
const { show } = useToast()
const { summary, recommendJobs, loading, error, refresh, ensure } = useDashboardSummary()

const query = ref('')
const selectedJob = ref<JobItem | null>(null)
const recommendationsEl = ref<HTMLElement | null>(null)

const filteredJobs = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  const list = recommendJobs.value
  if (!keyword) return list
  return list.filter((job) =>
    `${job.title} ${job.company}`.toLocaleLowerCase().includes(keyword),
  )
})

const emptyRecommendText = computed(() => {
  if (query.value.trim()) return '未找到与关键词匹配的推荐岗位。'
  return '暂无推荐结果。先上传简历并确认画像，再从「智能匹配」发起推荐。'
})

onMounted(() => {
  void ensure()
})

function handleSearch(value: string) {
  query.value = value
}

function handleSubmit(value: string) {
  query.value = value
  if (value.trim()) {
    recommendationsEl.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

function handleStatSelect(item: StatCardItem) {
  // 统计卡片对应真实页面，直接跳转
  const routeByTarget: Record<string, string> = {
    简历管理: '/resume',
    我的画像: '/profile',
    岗位探索: '/jobs',
    智能匹配: '/matching',
  }
  const to = routeByTarget[item.target]
  if (to) {
    router.push(to)
    return
  }
  show(`「${item.target}」页面开发中，敬请期待。`)
}

function handleGuide() {
  router.push('/profile')
}

function handleLogout() {
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <TopBar
      :notifications="summary?.notifications ?? []"
      :meta="summary?.studentMeta ?? ''"
      @search="handleSearch"
      @submit="handleSubmit"
      @logout="handleLogout"
    />
    <SideNav active-key="dashboard" />

    <main class="workspace" id="workbench">
      <!-- 加载中 / 加载失败 -->
      <template v-if="!summary">
        <div v-if="error" class="state-block" role="alert">
          <p class="state-title">工作台数据加载失败</p>
          <p class="state-desc">{{ error }}</p>
          <button type="button" class="state-retry" :disabled="loading" @click="refresh(true)">
            {{ loading ? '加载中…' : '重新加载' }}
          </button>
        </div>
        <div v-else class="state-block" role="status" aria-live="polite">
          <span class="state-spinner" aria-hidden="true" />
          <p>正在加载工作台真实数据…</p>
        </div>
      </template>

      <div v-else class="dashboard">
        <!-- 数据源不可用说明（真实登记，不伪造统计） -->
        <div v-if="summary.dataNotes.length" class="data-notes" role="note">
          <strong>数据来源提示：</strong>
          <span v-for="(note, i) in summary.dataNotes" :key="i">{{ note }}<template v-if="i < summary.dataNotes.length - 1">；</template></span>
        </div>

        <WelcomeBanner :greeting="summary.greeting" :lines="summary.lines" />

        <StatsGrid :items="summary.statCards" @select="handleStatSelect" />

        <section class="feature-grid" aria-label="智能匹配与求职进度">
          <MatchPromo @start="router.push('/matching')" />
          <JobProgressPanel
            :steps="summary.progressSteps"
            :status="summary.progressStatus"
            @guide="handleGuide"
          />
        </section>

        <section class="analysis-grid" aria-label="推荐趋势与结果">
          <div class="column-left">
            <TrendCard />
            <ActivityCard :items="summary.activityItems" @more="router.push('/history')" />
          </div>
          <div class="column-right" ref="recommendationsEl">
            <RecommendCard
              :jobs="filteredJobs"
              :empty-text="emptyRecommendText"
              @select="selectedJob = $event"
              @more="router.push('/jobs')"
            />
            <NoticeCard :text="NOTICE_TEXT" />
          </div>
        </section>
      </div>
    </main>

    <JobDetailDialog :job="selectedJob" @close="selectedJob = null" />
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}
.workspace {
  margin-left: 198px;
  padding: 13px 16px 35px 15px;
  padding-top: 75px;
  min-height: 100vh;
  background: radial-gradient(ellipse at 48% 13%, #e9f4ff 0%, #f5fbff 43%, #f8fbff 100%);
}
.dashboard {
  max-width: 1178px;
}
.data-notes {
  background: #fff7e8;
  border: 1px solid #ffe1b0;
  color: #8a5a12;
  border-radius: 9px;
  padding: 9px 13px;
  font-size: 12px;
  margin-bottom: 13px;
  line-height: 1.7;
}
.state-block {
  max-width: 1178px;
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(35, 84, 138, 0.06);
  color: #6a789a;
  font-size: 13px;
}
.state-spinner {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 3px solid #cfe0ff;
  border-top-color: #2a75ff;
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.state-title {
  font-size: 15px;
  font-weight: 800;
  color: #22314f;
  margin: 0;
}
.state-desc {
  margin: 0;
  max-width: 520px;
  text-align: center;
  line-height: 1.7;
}
.state-retry {
  border: 0;
  border-radius: 7px;
  background: #2a75ff;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  padding: 9px 22px;
}
.state-retry:hover {
  background: #1c62e0;
}
.state-retry:disabled {
  background: #9dbcf5;
  cursor: not-allowed;
}
.feature-grid {
  display: grid;
  grid-template-columns: 503px minmax(0, 1fr);
  gap: 16px;
  margin-bottom: 15px;
}
.analysis-grid {
  display: grid;
  grid-template-columns: 612px minmax(0, 1fr);
  gap: 15px;
}
.column-left,
.column-right {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

@media (max-width: 1380px) {
  .feature-grid {
    grid-template-columns: 43% minmax(0, 1fr);
  }
  .analysis-grid {
    grid-template-columns: 52% minmax(0, 1fr);
  }
}
@media (max-width: 1100px) {
  .workspace {
    margin-left: 76px;
  }
  .feature-grid {
    grid-template-columns: 41% minmax(0, 1fr);
  }
  .analysis-grid {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 830px) {
  .workspace {
    padding-top: 71px;
    padding-right: 13px;
  }
  .feature-grid,
  .analysis-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .feature-grid {
    gap: 12px;
  }
  .analysis-grid {
    gap: 13px;
  }
}
@media (max-width: 540px) {
  .workspace {
    margin-left: 0;
    padding: 70px 10px 82px;
  }
}
</style>
