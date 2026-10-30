<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import { useToast } from '@/composables/useToast'
import {
  categoryOptions,
  cityOptions,
  educationOptions,
  heroCopy,
  hotTags,
  jobList,
  selectedFilters,
  sortOptions,
} from '@/data/jobs'
import type { JobCardItem } from '@/types'

const router = useRouter()
const { show } = useToast()

const keyword = ref('')
const city = ref('all')
const category = ref('all')
const education = ref('all')
const salaryMin = ref('')
const salaryMax = ref('')
const activeSort = ref('综合排序')
const viewMode = ref<'list' | 'card'>('list')
const activeTag = ref('')
const chips = ref([...selectedFilters])

const filteredJobs = computed(() => {
  let list = [...jobList]
  const kw = keyword.value.trim().toLowerCase()
  if (kw) {
    list = list.filter((job) => `${job.title} ${job.company}`.toLowerCase().includes(kw))
  }
  if (category.value !== 'all') {
    list = list.filter((job) => job.category === category.value)
  }
  if (activeTag.value) {
    list = list.filter((job) => job.tags.includes(activeTag.value))
  }
  if (activeSort.value === '薪资从高到低') {
    list.sort((a, b) => parseInt(b.salary) - parseInt(a.salary))
  } else if (activeSort.value === '薪资从低到高') {
    list.sort((a, b) => parseInt(a.salary) - parseInt(b.salary))
  } else if (activeSort.value === '匹配度从高到低') {
    list.sort((a, b) => b.match - a.match)
  }
  return list
})

function handleSearch() {
  show(`搜索「${keyword.value || '全部岗位'}」（演示数据）`)
}

function handleReset() {
  keyword.value = ''
  city.value = 'all'
  category.value = 'all'
  education.value = 'all'
  salaryMin.value = ''
  salaryMax.value = ''
  activeTag.value = ''
  chips.value = []
  show('已重置全部筛选条件')
}

function removeChip(key: string) {
  chips.value = chips.value.filter((c) => c.key !== key)
}

function handleTagClick(tag: string) {
  activeTag.value = activeTag.value === tag ? '' : tag
}

function handleViewDetail(job: JobCardItem) {
  router.push(`/job/${job.id}`)
}

function handleAddMatch(job: JobCardItem) {
  show(`「${job.title}」已加入匹配队列（演示）`)
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <SideNav active-key="jobs" />

    <main class="workspace">
      <section class="hero">
        <div class="hero-content">
          <h1>{{ heroCopy.title }}</h1>
          <p v-for="(line, i) in heroCopy.lines" :key="i">{{ line }}</p>
        </div>
      </section>

      <section class="panel filter-panel">
        <div class="filter-row">
          <div class="filter-item keyword-item">
            <span class="filter-label">关键词</span>
            <div class="input-shell">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>
              <input v-model="keyword" placeholder="搜索岗位名称、公司名称或关键词，如：前端开发、产品经理、字节跳动" @keyup.enter="handleSearch" />
            </div>
          </div>
          <div class="filter-item">
            <span class="filter-label">城市</span>
            <select v-model="city" class="select-shell">
              <option v-for="opt in cityOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
        </div>
        <div class="filter-row">
          <div class="filter-item">
            <span class="filter-label">岗位类别</span>
            <select v-model="category" class="select-shell">
              <option v-for="opt in categoryOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="filter-item">
            <span class="filter-label">学历要求</span>
            <select v-model="education" class="select-shell">
              <option v-for="opt in educationOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="filter-item">
            <span class="filter-label">技能标签</span>
            <select class="select-shell">
              <option>请选择技能标签</option>
              <option v-for="tag in hotTags" :key="tag">{{ tag }}</option>
            </select>
          </div>
          <div class="filter-item salary-item">
            <span class="filter-label">薪资范围</span>
            <div class="salary-range">
              <input v-model="salaryMin" placeholder="最低薪资" />
              <span class="dash">—</span>
              <input v-model="salaryMax" placeholder="最高薪资" />
              <span class="unit">K</span>
            </div>
          </div>
          <button class="btn-search" type="button" @click="handleSearch">搜索岗位</button>
        </div>
        <div class="hot-tags">
          <span class="filter-label">热门标签：</span>
          <button
            v-for="tag in hotTags"
            :key="tag"
            type="button"
            class="hot-tag"
            :class="{ active: activeTag === tag }"
            @click="handleTagClick(tag)"
          >
            {{ tag }}
          </button>
          <button type="button" class="hot-tag more">更多 ∨</button>
          <button type="button" class="reset-btn" @click="handleReset">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6M23 20v-6h-6" /><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" /></svg>
            重置筛选
          </button>
        </div>
      </section>

      <section class="result-bar">
        <div class="result-count">共 <b>1,286</b> 个岗位</div>
        <div class="chips">
          <span>已选条件：</span>
          <span v-for="chip in chips" :key="chip.key" class="chip">
            {{ chip.label }}
            <button type="button" @click="removeChip(chip.key)">×</button>
          </span>
          <button v-if="chips.length" type="button" class="clear-all" @click="chips = []">清空全部</button>
        </div>
      </section>

      <section class="panel list-panel">
        <div class="sort-bar">
          <div class="sort-tabs">
            <button
              v-for="opt in sortOptions"
              :key="opt"
              type="button"
              class="sort-tab"
              :class="{ active: activeSort === opt }"
              @click="activeSort = opt"
            >
              {{ opt }}
            </button>
          </div>
          <div class="view-toggle">
            <button type="button" class="view-btn" :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></svg>
              列表模式
            </button>
            <button type="button" class="view-btn" :class="{ active: viewMode === 'card' }" @click="viewMode = 'card'">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></svg>
              卡片模式
            </button>
          </div>
        </div>

        <div class="job-list" :class="{ 'card-mode': viewMode === 'card' }">
          <article v-for="job in filteredJobs" :key="job.id" class="job-card">
            <img class="job-logo" :src="job.logo" :alt="job.logoAlt" />
            <div class="job-main">
              <div class="job-title-row">
                <h3>{{ job.title }}</h3>
                <span class="badge-blue">校招</span>
              </div>
              <div class="job-company">{{ job.company }} <i /> {{ job.industry }} <i /> {{ job.scale }}</div>
              <div class="job-meta">
                <span>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></svg>
                  {{ job.location }}
                </span>
                <span>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
                  {{ job.publishTime }}
                </span>
              </div>
              <div class="job-tags">
                <span v-for="tag in job.tags" :key="tag" class="tag">{{ tag }}</span>
              </div>
              <p class="job-desc">{{ job.desc }}</p>
            </div>
            <div class="job-side">
              <div class="job-salary">{{ job.salary }} · {{ job.months }}薪</div>
              <div class="job-match">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9" /><path d="M8 12l3 3 5-6" /></svg>
                {{ job.match }}% 匹配度
              </div>
              <div class="job-actions">
                <button type="button" class="btn-detail" @click="handleViewDetail(job)">查看详情</button>
                <button type="button" class="btn-match" @click="handleAddMatch(job)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" /></svg>
                  加入匹配
                </button>
              </div>
            </div>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.app-shell { min-height: 100vh; }
.workspace {
  margin-left: 198px;
  padding: 75px 57px 35px 17px;
  background: linear-gradient(180deg, #f4f9ff 0%, #f8fbff 100%);
}
.hero {
  height: 138px;
  border-radius: 12px;
  background: linear-gradient(110deg, #eff7ff 0%, #daeaff 47%, #b8d8ff 75%, #c1d3ff 100%);
  margin-bottom: 12px;
  padding: 0 37px;
  display: flex;
  align-items: center;
}
.hero-content h1 { font-size: 30px; margin: 0 0 8px; font-weight: 800; letter-spacing: -1px; color: #101d46; }
.hero-content p { margin: 0; line-height: 1.75; color: #41567f; font-size: 14px; font-weight: 500; }

.panel {
  background: white;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 4px 14px rgba(45, 78, 139, 0.045);
}
.filter-panel { margin-bottom: 12px; }
.filter-row {
  display: flex;
  gap: 14px;
  align-items: flex-end;
  margin-bottom: 13px;
  flex-wrap: wrap;
}
.filter-item { display: flex; flex-direction: column; gap: 6px; }
.filter-label { font-size: 12px; font-weight: 700; color: #4b5a7c; }
.keyword-item { flex: 1; min-width: 320px; }
.input-shell {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  padding: 0 12px;
  color: #9ca8bf;
}
.input-shell svg { width: 15px; height: 15px; flex-shrink: 0; }
.input-shell input { flex: 1; border: 0; outline: 0; font-size: 12px; color: #243457; min-width: 0; }
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
.salary-range {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 38px;
}
.salary-range input {
  width: 92px;
  height: 38px;
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  padding: 0 10px;
  font-size: 12px;
  outline: 0;
}
.dash { color: #9ca8bf; }
.unit { color: #4b5a7c; font-weight: 700; }
.btn-search {
  height: 38px;
  padding: 0 30px;
  background: #2168ff;
  color: white;
  border: 0;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
  margin-left: auto;
}
.btn-search:hover { background: #1557e0; }
.hot-tags { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.hot-tag {
  border: 1px solid #dde5f0;
  background: #f7f9fc;
  color: #5b6b8d;
  border-radius: 14px;
  padding: 4px 12px;
  font-size: 11px;
}
.hot-tag.active { background: #e3edff; border-color: #2168ff; color: #2168ff; font-weight: 700; }
.reset-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 0;
  background: none;
  color: #5b6b8d;
  font-size: 12px;
}
.reset-btn svg { width: 14px; height: 14px; }

.result-bar {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.result-count { font-size: 14px; color: #4b5a7c; }
.result-count b { font-size: 20px; color: #2168ff; margin: 0 3px; }
.chips { display: flex; align-items: center; gap: 8px; margin-left: auto; font-size: 12px; color: #7b8aa9; flex-wrap: wrap; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: #e8f1ff;
  color: #2168ff;
  border-radius: 4px;
  padding: 3px 8px;
  font-weight: 700;
}
.chip button { border: 0; background: none; color: #2168ff; font-size: 13px; padding: 0; }
.clear-all { border: 0; background: none; color: #2168ff; font-size: 12px; }

.sort-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  border-bottom: 1px solid #eef2f8;
}
.sort-tabs { display: flex; gap: 26px; }
.sort-tab {
  border: 0;
  background: none;
  padding: 0 2px 12px;
  font-size: 13px;
  color: #66758f;
  position: relative;
}
.sort-tab.active { color: #2168ff; font-weight: 800; }
.sort-tab.active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 3px;
  background: #2168ff;
  border-radius: 2px;
}
.view-toggle { display: flex; gap: 8px; padding-bottom: 8px; }
.view-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid #d9e2ef;
  background: white;
  color: #66758f;
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
}
.view-btn svg { width: 14px; height: 14px; }
.view-btn.active { background: #2168ff; border-color: #2168ff; color: white; }

.job-list { display: flex; flex-direction: column; gap: 12px; }
.job-card {
  display: flex;
  gap: 16px;
  border: 1px solid #e8eef7;
  border-radius: 10px;
  padding: 16px 18px;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.job-card:hover { border-color: #b9d2ff; box-shadow: 0 6px 18px rgba(45, 78, 139, 0.08); }
.job-logo { width: 52px; height: 52px; object-fit: contain; flex-shrink: 0; }
.job-main { flex: 1; min-width: 0; }
.job-title-row { display: flex; align-items: center; gap: 9px; }
.job-title-row h3 { margin: 0; font-size: 16px; font-weight: 800; color: #16234a; }
.badge-blue {
  background: #e8f1ff;
  color: #2168ff;
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 4px;
  font-weight: 700;
}
.job-company { font-size: 12px; color: #7b8aa9; margin: 6px 0; }
.job-company i { display: inline-block; width: 1px; height: 10px; background: #d5deeb; margin: 0 8px; vertical-align: middle; }
.job-meta { display: flex; gap: 18px; font-size: 11px; color: #8b98b2; margin-bottom: 8px; }
.job-meta span { display: inline-flex; align-items: center; gap: 4px; }
.job-meta svg { width: 13px; height: 13px; }
.job-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.tag {
  background: #f2f5fa;
  color: #6b7a99;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
}
.job-desc {
  margin: 0;
  font-size: 11px;
  line-height: 1.65;
  color: #8592ab;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.job-side {
  width: 210px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 9px;
}
.job-salary { font-size: 18px; font-weight: 800; color: #ff6b1a; }
.job-match {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #03b58c;
  font-size: 12px;
  font-weight: 700;
}
.job-match svg { width: 15px; height: 15px; }
.job-actions { display: flex; gap: 8px; }
.btn-detail {
  border: 1px solid #2168ff;
  background: white;
  color: #2168ff;
  border-radius: 6px;
  padding: 7px 14px;
  font-size: 12px;
  font-weight: 700;
}
.btn-match {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 0;
  background: #2168ff;
  color: white;
  border-radius: 6px;
  padding: 7px 14px;
  font-size: 12px;
  font-weight: 700;
}
.btn-match svg { width: 13px; height: 13px; }

.job-list.card-mode { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.job-list.card-mode .job-card { flex-direction: column; }
.job-list.card-mode .job-side { width: 100%; align-items: flex-start; }

@media (max-width: 1190px) {
  .workspace { padding-right: 18px; }
}
@media (max-width: 1000px) {
  .workspace { margin-left: 76px; }
  .job-list.card-mode { grid-template-columns: 1fr; }
}
@media (max-width: 540px) {
  .workspace { margin-left: 0; padding: 70px 10px 82px; }
  .job-card { flex-direction: column; }
  .job-side { width: 100%; align-items: flex-start; }
}
</style>
