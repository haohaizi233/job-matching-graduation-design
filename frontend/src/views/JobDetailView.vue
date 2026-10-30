<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import { useToast } from '@/composables/useToast'
import { jobDetail, jobList } from '@/data/jobs'

const router = useRouter()
const route = useRoute()
const { show } = useToast()

const tabs = ['岗位详情', '公司介绍', '原始 JD', '结构化画像'] as const
type DetailTab = (typeof tabs)[number]

const activeTab = ref<DetailTab>('岗位详情')
const bookmarked = ref(false)

const job = computed(() => {
  const id = Number(route.params.id)
  return jobList.find((item) => item.id === id) ?? jobList[0]
})

const detail = jobDetail

function handleBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/jobs')
  }
}

function handleBookmark() {
  bookmarked.value = !bookmarked.value
  show(bookmarked.value ? `已收藏「${job.value.title}」` : `已取消收藏「${job.value.title}」`)
}

function handleApply() {
  show(`已发起对「${job.value.title}」的投递（演示，未接入投递流程）`)
}

function handleMatchInfo() {
  show('匹配度由技能、教育、项目与求职意向四维加权计算（演示数据）')
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <SideNav active-key="jobs" />

    <main class="workspace">
      <nav class="breadcrumb" aria-label="面包屑">
        <button type="button" class="crumb-link" @click="router.push('/jobs')">岗位探索</button>
        <span class="crumb-sep">/</span>
        <span class="crumb-current">岗位详情</span>
        <button type="button" class="back-btn" @click="handleBack">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
          返回
        </button>
      </nav>

      <section class="panel job-head-card">
        <img class="job-logo" :src="job.logo" :alt="job.logoAlt" />
        <div class="job-head-main">
          <div class="job-title-row">
            <h1>{{ job.title }}</h1>
            <span class="badge-blue">校招</span>
          </div>
          <div class="job-company">{{ job.company }} <i /> {{ job.industry }} <i /> {{ job.scale }}</div>
          <div class="job-tags">
            <span v-for="tag in job.tags" :key="tag" class="tag">{{ tag }}</span>
          </div>
          <div class="job-meta">
            <span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></svg>
              {{ job.location }}
            </span>
            <span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
              {{ job.publishTime }}
            </span>
            <span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16v12H4zM8 7V5h8v2" /></svg>
              {{ job.education }} · {{ job.experience }}
            </span>
          </div>
        </div>
        <div class="job-head-side">
          <div class="job-salary">{{ job.salary }} · {{ job.months }}薪</div>
          <div class="head-actions">
            <button type="button" class="btn-outline" @click="handleBookmark">
              <svg viewBox="0 0 24 24" :fill="bookmarked ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" /></svg>
              {{ bookmarked ? '已收藏' : '收藏岗位' }}
            </button>
            <button type="button" class="btn-primary" @click="handleApply">立即投递</button>
          </div>
        </div>
      </section>

      <div class="content-grid">
        <section class="panel detail-panel">
          <div class="tab-bar">
            <button
              v-for="tab in tabs"
              :key="tab"
              type="button"
              class="tab"
              :class="{ active: activeTab === tab }"
              @click="activeTab = tab"
            >
              {{ tab }}
            </button>
          </div>

          <template v-if="activeTab === '岗位详情'">
            <div class="block">
              <h2 class="block-title">岗位职责</h2>
              <ol class="block-list">
                <li v-for="(item, i) in detail.duties" :key="i">{{ item }}</li>
              </ol>
            </div>
            <div class="block">
              <h2 class="block-title">任职要求</h2>
              <ol class="block-list">
                <li v-for="(item, i) in detail.requirements" :key="i">{{ item }}</li>
              </ol>
            </div>
            <div class="block">
              <h2 class="block-title">技能要求</h2>
              <div v-for="group in detail.skillGroups" :key="group.group" class="skill-group">
                <span class="skill-group-label">{{ group.group }}</span>
                <div class="skill-chips">
                  <span v-for="skill in group.skills" :key="skill" class="tag">{{ skill }}</span>
                </div>
              </div>
            </div>
            <div class="block">
              <h2 class="block-title">公司介绍</h2>
              <p class="block-paragraph">{{ detail.companyIntro }}</p>
            </div>
          </template>

          <template v-else-if="activeTab === '公司介绍'">
            <div class="block">
              <h2 class="block-title">{{ detail.company }}</h2>
              <div class="company-facts">
                <div class="fact"><span>所属行业</span><strong>{{ detail.industry }}</strong></div>
                <div class="fact"><span>公司规模</span><strong>{{ detail.scale }}</strong></div>
                <div class="fact"><span>融资阶段</span><strong>{{ detail.status }}</strong></div>
                <div class="fact"><span>工作地点</span><strong>{{ detail.location }}</strong></div>
              </div>
              <p class="block-paragraph">{{ detail.companyIntro }}</p>
            </div>
          </template>

          <template v-else-if="activeTab === '原始 JD'">
            <div class="block">
              <h2 class="block-title">原始 JD</h2>
              <pre class="jd-raw">{{ detail.duties.join('\n') }}
{{ detail.requirements.join('\n') }}</pre>
            </div>
          </template>

          <template v-else>
            <div class="block">
              <h2 class="block-title">结构化画像</h2>
              <div class="condition-table">
                <div v-for="item in detail.conditionMatch" :key="item.label" class="condition-row">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </div>
              </div>
              <div class="block">
                <h2 class="block-title">技能标签汇总</h2>
                <div class="skill-chips">
                  <span v-for="group in detail.skillGroups" :key="group.group">
                    <span v-for="skill in group.skills" :key="skill" class="tag">{{ skill }}</span>
                  </span>
                </div>
              </div>
            </div>
          </template>
        </section>

        <aside class="side-column">
          <section class="panel match-panel">
            <h2 class="panel-title">
              匹配度预览
              <button type="button" class="info-btn" title="匹配度说明" @click="handleMatchInfo">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" /></svg>
              </button>
            </h2>
            <div class="ring-wrap">
              <svg viewBox="0 0 120 120" class="ring">
                <circle cx="60" cy="60" r="50" class="ring-track" />
                <circle
                  cx="60"
                  cy="60"
                  r="50"
                  class="ring-value"
                  :style="{ strokeDasharray: (detail.matchPreview.percent / 100) * 2 * Math.PI * 50 + ' ' + 2 * Math.PI * 50 }"
                />
              </svg>
              <div class="ring-text">
                <strong>{{ detail.matchPreview.percent }}%</strong>
                <span>{{ detail.matchPreview.level }}</span>
              </div>
            </div>
            <p class="match-desc">{{ detail.matchPreview.desc }}</p>
          </section>

          <section class="panel">
            <h2 class="panel-title">技能匹配 {{ detail.skillMatch.matched.length }}/{{ detail.skillMatch.matched.length + detail.skillMatch.improve.length }}</h2>
            <h3 class="side-subtitle">已掌握</h3>
            <div class="skill-chips">
              <span v-for="skill in detail.skillMatch.matched" :key="skill" class="tag good">{{ skill }}</span>
            </div>
            <h3 class="side-subtitle">待提升</h3>
            <div class="skill-chips">
              <span v-for="skill in detail.skillMatch.improve" :key="skill" class="tag warn">{{ skill }}</span>
            </div>
          </section>

          <section class="panel">
            <h2 class="panel-title">其他条件匹配</h2>
            <div class="condition-table">
              <div v-for="item in detail.conditionMatch" :key="item.label" class="condition-row">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
          </section>

          <section class="panel">
            <h2 class="panel-title">行动建议</h2>
            <ol class="advice-list">
              <li v-for="(item, i) in detail.advice" :key="i">{{ item }}</li>
            </ol>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>

<style scoped>
.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 12px;
}
.crumb-link {
  border: 0;
  background: none;
  color: #2168ff;
  font-size: 12px;
  padding: 0;
}
.crumb-sep {
  color: #b7c1d3;
}
.crumb-current {
  color: #7b8aa9;
}
.back-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid #d9e2ef;
  background: white;
  color: #4b5a7c;
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 700;
}
.back-btn svg {
  width: 14px;
  height: 14px;
}

.panel {
  background: white;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 4px 14px rgba(45, 78, 139, 0.045);
  margin-bottom: 12px;
}
.panel-title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 800;
  color: #16234a;
  display: flex;
  align-items: center;
  gap: 7px;
}
.info-btn {
  border: 0;
  background: none;
  color: #9ca8bf;
  padding: 0;
  display: inline-flex;
}
.info-btn svg {
  width: 15px;
  height: 15px;
}

.job-head-card {
  display: flex;
  gap: 18px;
  align-items: flex-start;
}
.job-logo {
  width: 62px;
  height: 62px;
  object-fit: contain;
  flex-shrink: 0;
}
.job-head-main {
  flex: 1;
  min-width: 0;
}
.job-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.job-title-row h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #16234a;
}
.badge-blue {
  background: #e8f1ff;
  color: #2168ff;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 700;
}
.job-company {
  font-size: 12px;
  color: #7b8aa9;
  margin: 8px 0;
}
.job-company i {
  display: inline-block;
  width: 1px;
  height: 10px;
  background: #d5deeb;
  margin: 0 8px;
  vertical-align: middle;
}
.job-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.tag {
  background: #f2f5fa;
  color: #6b7a99;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
  display: inline-block;
  margin: 2px 4px 2px 0;
}
.tag.good {
  background: #e5f8f2;
  color: #03b58c;
}
.tag.warn {
  background: #fff3e3;
  color: #ff8a1a;
}
.job-meta {
  display: flex;
  gap: 18px;
  font-size: 11px;
  color: #8b98b2;
  flex-wrap: wrap;
}
.job-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.job-meta svg {
  width: 13px;
  height: 13px;
}
.job-head-side {
  text-align: right;
  flex-shrink: 0;
}
.job-salary {
  font-size: 22px;
  font-weight: 800;
  color: #ff6b1a;
  margin-bottom: 12px;
}
.head-actions {
  display: flex;
  gap: 8px;
}
.btn-outline {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid #2168ff;
  background: white;
  color: #2168ff;
  border-radius: 6px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 700;
}
.btn-outline svg {
  width: 14px;
  height: 14px;
}
.btn-primary {
  border: 0;
  background: #2168ff;
  color: white;
  border-radius: 6px;
  padding: 8px 20px;
  font-size: 12px;
  font-weight: 700;
}
.btn-primary:hover {
  background: #1557e0;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 310px;
  gap: 12px;
  align-items: start;
}
.side-column {
  display: flex;
  flex-direction: column;
}

.tab-bar {
  display: flex;
  gap: 26px;
  border-bottom: 1px solid #eef2f8;
  margin-bottom: 16px;
}
.tab {
  border: 0;
  background: none;
  padding: 0 2px 12px;
  font-size: 13px;
  color: #66758f;
  position: relative;
}
.tab.active {
  color: #2168ff;
  font-weight: 800;
}
.tab.active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 3px;
  background: #2168ff;
  border-radius: 2px;
}

.block {
  margin-bottom: 20px;
}
.block-title {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 800;
  color: #16234a;
}
.block-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 2;
  color: #4b5a7c;
}
.block-paragraph {
  margin: 0;
  font-size: 12px;
  line-height: 2;
  color: #4b5a7c;
}
.skill-group {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
}
.skill-group-label {
  font-size: 11px;
  font-weight: 700;
  color: #4b5a7c;
  width: 62px;
  flex-shrink: 0;
  padding-top: 4px;
}
.skill-chips {
  display: flex;
  flex-wrap: wrap;
}
.jd-raw {
  margin: 0;
  background: #f7f9fc;
  border: 1px solid #e8eef7;
  border-radius: 8px;
  padding: 16px;
  font-size: 12px;
  line-height: 2;
  color: #4b5a7c;
  white-space: pre-wrap;
  font-family: inherit;
}
.company-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.fact {
  background: #f7faff;
  border: 1px solid #e8eef7;
  border-radius: 8px;
  padding: 10px 13px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fact span {
  font-size: 11px;
  color: #8592ab;
}
.fact strong {
  font-size: 13px;
  color: #16234a;
}

.ring-wrap {
  position: relative;
  width: 150px;
  height: 150px;
  margin: 6px auto 12px;
}
.ring {
  width: 150px;
  height: 150px;
  transform: rotate(-90deg);
}
.ring-track {
  fill: none;
  stroke: #eef2f8;
  stroke-width: 11;
}
.ring-value {
  fill: none;
  stroke: #2168ff;
  stroke-width: 11;
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
  font-size: 30px;
  color: #2168ff;
}
.ring-text span {
  font-size: 12px;
  color: #03b58c;
  font-weight: 700;
}
.match-desc {
  margin: 0;
  font-size: 11px;
  line-height: 1.8;
  color: #8592ab;
  text-align: center;
}
.side-subtitle {
  margin: 0 0 7px;
  font-size: 11px;
  color: #8b98b2;
  font-weight: 700;
}
.condition-table {
  display: flex;
  flex-direction: column;
}
.condition-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px solid #f0f3f9;
  font-size: 12px;
}
.condition-row:last-child {
  border-bottom: 0;
}
.condition-row span {
  color: #8592ab;
}
.condition-row strong {
  color: #16234a;
}
.advice-list {
  margin: 0;
  padding-left: 18px;
  font-size: 11px;
  line-height: 2;
  color: #4b5a7c;
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
  .job-head-card {
    flex-direction: column;
  }
  .job-head-side {
    text-align: left;
    width: 100%;
  }
}
</style>
