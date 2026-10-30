<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import { listJobs } from '@/api/jobs'
import { dateOnly, dateTime, GENERIC_LOGO, jobProfileView, mapRunToHistory } from '@/api/mappers'
import { createRecommendation, getRun, listRuns } from '@/api/recommendations'
import type { JobRow } from '@/api/types'
import { useToast } from '@/composables/useToast'
import { heroCopy, statusOptions, statusText } from '@/data/history'
import type { HistoryJobItem, HistoryRecordItem } from '@/types/history'

const router = useRouter()
const { show } = useToast()

const activeStatus = ref<'all' | 'done' | 'expired' | 'pending'>('all')
const page = ref(1)
const pageSize = 3
const selectedId = ref<number | string>('')
const checkedJobs = ref<Array<number | string>>([])

// 联调：推荐历史来自业务 API（每次匹配一条 run，含岗位快照）
const records = ref<HistoryRecordItem[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const [runsPage, jobRows] = await Promise.all([listRuns(1, 50), listJobs()])
    const jobsMap = new Map<string, JobRow>(jobRows.map((row) => [row.id, row]))

    const built: HistoryRecordItem[] = []
    for (const run of runsPage.items) {
      const record = mapRunToHistory(run)
      const detail = await getRun(run.id)
      const items = detail.items || []
      const jobs: HistoryJobItem[] = items.map((item) => {
        const row = jobsMap.get(item.job_id)
        const view = row ? jobProfileView(row) : null
        return {
          id: item.job_id,
          title: row?.title || '未命名岗位',
          company: view?.employer || '未标注企业',
          salary: view?.salary || '面议',
          match: Math.round(item.score * 100),
          logo: GENERIC_LOGO,
          logoAlt: view?.employer || '未标注企业',
        }
      })
      record.jobs = jobs
      record.avgMatch = items.length
        ? Math.round(items.reduce((sum, i) => sum + i.score * 100, 0) / items.length)
        : 0
      record.highMatchCount = items.filter((i) => i.score * 100 >= 85).length
      record.jobCount = jobs.length
      record.time = dateTime(run.created_at) || dateOnly(run.created_at)
      built.push(record)
    }
    records.value = built
    selectedId.value = built[0]?.id ?? ''
  } catch (e) {
    show(e instanceof Error ? e.message : '推荐历史加载失败')
  } finally {
    loading.value = false
  }
})

const filteredRecords = computed(() => {
  if (activeStatus.value === 'all') return records.value
  return records.value.filter((record) => record.status === activeStatus.value)
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRecords.value.length / pageSize)))

const pageRecords = computed(() => {
  const start = (page.value - 1) * pageSize
  return filteredRecords.value.slice(start, start + pageSize)
})

const selectedRecord = computed<HistoryRecordItem | undefined>(() => {
  return (
    records.value.find((record) => record.id === selectedId.value) ?? filteredRecords.value[0] ?? undefined
  )
})

function handleStatusChange(value: typeof activeStatus.value) {
  activeStatus.value = value
  page.value = 1
}

function handleSelect(record: HistoryRecordItem) {
  selectedId.value = record.id
  checkedJobs.value = []
}

function toggleChecked(id: number | string) {
  checkedJobs.value = checkedJobs.value.includes(id)
    ? checkedJobs.value.filter((i) => i !== id)
    : [...checkedJobs.value, id]
}

async function handleRerun() {
  if (checkedJobs.value.length > 0) {
    show(`已选中 ${checkedJobs.value.length} 个岗位，正在重新匹配…`)
    try {
      await createRecommendation({ mode: 'baseline', jobIds: checkedJobs.value.map(String) })
      show('重新匹配完成')
    } catch (e) {
      show(e instanceof Error ? e.message : '重新匹配失败')
    }
  }
  router.push('/matching')
}

function handleViewDetail(id: number | string) {
  router.push(`/job/${id}`)
}

function handleDemo(name: string) {
  show(`「${name}」功能演示，尚未连接业务后端。`)
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <SideNav active-key="history" />

    <main class="workspace">
      <section class="hero">
        <div class="hero-content">
          <h1>{{ heroCopy.title }}</h1>
          <p v-for="(line, i) in heroCopy.lines" :key="i">{{ line }}</p>
        </div>
      </section>

      <section class="panel history-panel">
        <div class="panel-head">
          <h2 class="panel-title">历史记录</h2>
          <div class="status-tabs">
            <button
              v-for="opt in statusOptions"
              :key="opt.value"
              type="button"
              class="status-tab"
              :class="{ active: activeStatus === opt.value }"
              @click="handleStatusChange(opt.value)"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>

        <div class="record-list">
          <button
            v-for="record in pageRecords"
            :key="record.id"
            type="button"
            class="record-row"
            :class="{ active: selectedRecord?.id === record.id }"
            @click="handleSelect(record)"
          >
            <div class="record-main">
              <div class="record-title">
                <span class="record-time">{{ record.time }}</span>
                <span class="status-badge" :class="record.status">{{ statusText[record.status] }}</span>
              </div>
              <div class="record-meta">
                <span>画像版本 {{ record.profileVersion }}</span>
                <i />
                <span>{{ record.mode }}</span>
                <i />
                <span>推荐 {{ record.jobCount }} 个岗位</span>
                <i />
                <span>高匹配 {{ record.highMatchCount }} 个</span>
              </div>
            </div>
            <div class="record-side">
              <div class="record-avg">{{ record.avgMatch }}%</div>
              <div class="record-avg-label">平均匹配度</div>
            </div>
          </button>

          <p v-if="pageRecords.length === 0" class="empty-tip">该状态下暂无历史记录。</p>
        </div>

        <div class="pagination">
          <button type="button" class="page-btn" :disabled="page <= 1" @click="page -= 1">上一页</button>
          <span class="page-info">{{ page }} / {{ totalPages }}</span>
          <button type="button" class="page-btn" :disabled="page >= totalPages" @click="page += 1">下一页</button>
        </div>
      </section>

      <section v-if="selectedRecord" class="panel result-panel">
        <div class="panel-head">
          <h2 class="panel-title">推荐结果 · {{ selectedRecord.time }}</h2>
          <div class="result-actions">
            <button type="button" class="btn-outline" @click="handleDemo('导出结果')">导出结果</button>
            <button type="button" class="btn-primary" @click="handleRerun">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6M23 20v-6h-6" /><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" /></svg>
              重新运行匹配
            </button>
          </div>
        </div>

        <div class="result-summary">
          <div class="summary-item"><span>画像版本</span><strong>{{ selectedRecord.profileVersion }}</strong></div>
          <div class="summary-item"><span>推荐模式</span><strong>{{ selectedRecord.mode }}</strong></div>
          <div class="summary-item"><span>推荐岗位</span><strong>{{ selectedRecord.jobCount }} 个</strong></div>
          <div class="summary-item"><span>高匹配岗位</span><strong>{{ selectedRecord.highMatchCount }} 个</strong></div>
          <div class="summary-item"><span>平均匹配度</span><strong>{{ selectedRecord.avgMatch }}%</strong></div>
        </div>

        <div class="result-jobs">
          <label v-for="job in selectedRecord.jobs" :key="job.id" class="job-row">
            <input
              type="checkbox"
              :checked="checkedJobs.includes(job.id)"
              @change="toggleChecked(job.id)"
            />
            <img class="job-logo" :src="job.logo" :alt="job.logoAlt" />
            <div class="job-info">
              <strong>{{ job.title }}</strong>
              <span>{{ job.company }}</span>
            </div>
            <div class="job-match">{{ job.match }}% 匹配</div>
            <div class="job-salary">{{ job.salary }}</div>
            <button type="button" class="btn-link" @click.prevent="handleViewDetail(job.id)">查看详情</button>
          </label>
        </div>
      </section>
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

.status-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.status-tab {
  border: 1px solid #dde5f0;
  background: #f7f9fc;
  color: #5b6b8d;
  border-radius: 14px;
  padding: 4px 12px;
  font-size: 11px;
}
.status-tab.active {
  background: #e3edff;
  border-color: #2168ff;
  color: #2168ff;
  font-weight: 700;
}

.record-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.record-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid #e8eef7;
  border-radius: 10px;
  padding: 14px 18px;
  text-align: left;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.record-row:hover {
  border-color: #b9d2ff;
}
.record-row.active {
  border-color: #2168ff;
  background: #f5f9ff;
  box-shadow: 0 6px 18px rgba(45, 78, 139, 0.07);
}
.record-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.record-time {
  font-size: 14px;
  font-weight: 800;
  color: #16234a;
}
.status-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 700;
}
.status-badge.done {
  background: #e5f8f2;
  color: #03b58c;
}
.status-badge.pending {
  background: #e8f1ff;
  color: #2168ff;
}
.status-badge.expired {
  background: #f2f4f8;
  color: #8b98b2;
}
.record-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 7px;
  font-size: 11px;
  color: #8592ab;
}
.record-meta i {
  display: inline-block;
  width: 1px;
  height: 9px;
  background: #d5deeb;
}
.record-side {
  text-align: center;
  flex-shrink: 0;
}
.record-avg {
  font-size: 20px;
  font-weight: 800;
  color: #2168ff;
}
.record-avg-label {
  font-size: 10px;
  color: #8b98b2;
}
.empty-tip {
  text-align: center;
  color: #8592ab;
  font-size: 13px;
  padding: 24px 0;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 14px;
}
.page-btn {
  border: 1px solid #d9e2ef;
  background: white;
  color: #4b5a7c;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 700;
}
.page-btn:disabled {
  color: #b7c1d3;
  cursor: not-allowed;
}
.page-info {
  font-size: 12px;
  color: #7b8aa9;
}

.result-actions {
  display: flex;
  gap: 8px;
}
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 18px;
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
.btn-primary svg {
  width: 14px;
  height: 14px;
}
.btn-outline {
  height: 36px;
  padding: 0 16px;
  border: 1px solid #2168ff;
  background: white;
  color: #2168ff;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
}

.result-summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.summary-item {
  flex: 1;
  min-width: 130px;
  background: #f7faff;
  border: 1px solid #e8eef7;
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.summary-item span {
  font-size: 11px;
  color: #8592ab;
}
.summary-item strong {
  font-size: 14px;
  color: #16234a;
}

.result-jobs {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.job-row {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid #e8eef7;
  border-radius: 8px;
  padding: 10px 14px;
  cursor: pointer;
}
.job-row:hover {
  border-color: #b9d2ff;
}
.job-row input {
  accent-color: #2168ff;
  width: 15px;
  height: 15px;
  flex-shrink: 0;
}
.job-logo {
  width: 36px;
  height: 36px;
  object-fit: contain;
  flex-shrink: 0;
}
.job-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.job-info strong {
  font-size: 13px;
  color: #16234a;
}
.job-info span {
  font-size: 11px;
  color: #8592ab;
}
.job-match {
  font-size: 12px;
  font-weight: 700;
  color: #03b58c;
}
.job-salary {
  font-size: 13px;
  font-weight: 800;
  color: #ff6b1a;
}
.btn-link {
  border: 0;
  background: none;
  color: #2168ff;
  font-size: 12px;
  font-weight: 700;
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
}
@media (max-width: 540px) {
  .workspace {
    margin-left: 0;
    padding: 70px 10px 82px;
  }
  .record-row {
    flex-direction: column;
    align-items: flex-start;
  }
  .record-side {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .job-row {
    flex-wrap: wrap;
  }
}
</style>
