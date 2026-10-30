<script setup lang="ts">
import { computed, ref } from 'vue'
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
import { useToast } from '@/composables/useToast'
import {
  activityItems,
  jobItems,
  noticeText,
  progressStatus,
  progressSteps,
  statCards,
  welcomeCopy,
} from '@/data/dashboard'
import type { JobItem, StatCardItem } from '@/types'

const router = useRouter()
const { show } = useToast()

const query = ref('')
const selectedJob = ref<JobItem | null>(null)
const recommendationsEl = ref<HTMLElement | null>(null)

const filteredJobs = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return jobItems
  return jobItems.filter((job) =>
    `${job.title} ${job.company}`.toLocaleLowerCase().includes(keyword),
  )
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
  show(`「${item.target}」页面开发中，敬请期待。`)
}

function handleDemo(name: string) {
  show(`「${name}」属于页面导航演示，尚未连接实际业务后端。`)
}

function handleLogout() {
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <TopBar @search="handleSearch" @submit="handleSubmit" @logout="handleLogout" />
    <SideNav active-key="dashboard" />

    <main class="workspace" id="workbench">
      <div class="dashboard">
        <WelcomeBanner :greeting="welcomeCopy.greeting" :lines="welcomeCopy.lines" />

        <StatsGrid :items="statCards" @select="handleStatSelect" />

        <section class="feature-grid" aria-label="智能匹配与求职进度">
          <MatchPromo @start="handleDemo('智能匹配')" />
          <JobProgressPanel
            :steps="progressSteps"
            :status="progressStatus"
            @guide="handleDemo('详细指南')"
          />
        </section>

        <section class="analysis-grid" aria-label="推荐趋势与结果">
          <div class="column-left">
            <TrendCard />
            <ActivityCard :items="activityItems" @more="handleDemo('更多动态')" />
          </div>
          <div class="column-right" ref="recommendationsEl">
            <RecommendCard
              :jobs="filteredJobs"
              @select="selectedJob = $event"
              @more="handleDemo('岗位探索')"
            />
            <NoticeCard :text="noticeText" />
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
