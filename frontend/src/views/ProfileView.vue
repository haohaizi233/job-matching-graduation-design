<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import { dateTime } from '@/api/mappers'
import {
  mapProfileEducation,
  mapProfileInternships,
  mapProfileProjects,
  mapProfileSkills,
} from '@/api/mappers'
import { fieldValue, getProfile, getProfileVersion, listProfileVersions, saveProfile } from '@/api/profile'
import type { ProfileRow } from '@/api/types'
import { useAuth } from '@/composables/useAuth'
import { useToast } from '@/composables/useToast'
import {
  evidenceSources,
  profileHeroCopy,
  profileTags,
  radarData,
} from '@/data/profile'

const { show } = useToast()
const { state: authState } = useAuth()

// 画像来自业务 API（简历解析 + 人工修订的版本化画像）
const profile = ref<ProfileRow | null>(null)
const loading = ref(true)

async function refresh() {
  profile.value = await getProfile()
}

onMounted(async () => {
  try {
    await refresh()
  } catch (e) {
    show(e instanceof Error ? e.message : '画像加载失败')
  } finally {
    loading.value = false
  }
})

function valueOf(key: string): unknown {
  return fieldValue(profile.value, key)
}

function textOf(key: string, fallback = '—'): string {
  const v = valueOf(key)
  return v === null || v === undefined || v === '' ? fallback : String(v)
}

function citiesText(): string {
  const v = valueOf('preferred_cities')
  if (Array.isArray(v)) return v.map(String).join(' · ') || '—'
  return v ? String(v) : '—'
}

const profileBasic = computed(() => ({
  name: authState.user?.username || '我的画像',
  gender: '—',
  age: '—',
  birth: '—',
  phone: '—',
  email: authState.user?.email || '—',
  location: citiesText(),
  status: profile.value ? (profile.value.confirmed ? '已完善' : '待确认') : '待上传简历',
}))

const profileVersion = computed(() => ({
  version: profile.value ? `v${profile.value.profile_version}` : 'v—',
  status: profile.value?.confirmed ? '当前版本' : '待确认',
  updateTime: dateTime(profile.value?.created_at) || '—',
  desc: '基于简历解析生成，人工修订保留证据快照\n确认后可用于智能匹配',
}))

const jobIntention = computed(() => ({
  targetPosition: textOf('employment_intention'),
  industry: '—',
  city: citiesText(),
  salary: '—',
  entryTime: textOf('graduation_year') === '—' ? '—' : `${textOf('graduation_year')} 届`,
}))

const coreSkills = computed(() => mapProfileSkills(profile.value))
const education = computed(() => mapProfileEducation(profile.value))
const projects = computed(() => mapProfileProjects(profile.value))
const internships = computed(() => mapProfileInternships(profile.value))

const radarPoints = computed(() => {
  const cx = 100
  const cy = 100
  const radius = 72
  const n = radarData.dimensions.length
  return radarData.scores.map((score, i) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2
    const r = (score / 100) * radius
    return {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    }
  })
})

const radarAvgPoints = computed(() => {
  const cx = 100
  const cy = 100
  const radius = 72
  const n = radarData.dimensions.length
  return radarData.avgScores.map((score, i) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2
    const r = (score / 100) * radius
    return {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    }
  })
})

const radarLabels = computed(() => {
  const cx = 100
  const cy = 100
  const radius = 88
  const n = radarData.dimensions.length
  return radarData.dimensions.map((dim, i) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2
    return {
      text: dim,
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
      score: radarData.scores[i],
    }
  })
})

function handleEdit(section: string) {
  show(`编辑${section}功能开发中`)
}

function handleDemo(name: string) {
  show(`「${name}」功能开发中`)
}

// ------------------------------------------------ 人工修订（真实保存为新版本）
// 可编辑字段与后端 EDITABLE_PROFILE_FIELDS 同源；修改进 user_edits 覆盖层，
// 原始抽取证据保留（不静默覆盖）；保存后产生新版本，确认后才锁定用于推荐。
const editForm = reactive<Record<string, string>>({
  education_level: '',
  major: '',
  graduation_year: '',
  employment_intention: '',
  preferred_cities: '',
  employment_type: '',
})
const savingEdits = ref(false)

function fillEditForm(force = false) {
  for (const f of Object.keys(editForm)) {
    // 异步加载/刷新不得静默覆盖用户已输入的未保存内容（force 用于还原与保存后重填）
    if (!force && editTouched[f]) continue
    const v = fieldValue(profile.value, f)
    editForm[f] = v === undefined || v === null ? '' : String(v)
  }
}

const editTouched = reactive<Record<string, boolean>>({})

function markEditTouched(field: string) {
  editTouched[field] = true
}

watch(profile, () => fillEditForm(), { immediate: true })

function handleCancelEdit() {
  for (const f of Object.keys(editTouched)) editTouched[f] = false
  fillEditForm(true)
  show('已还原为当前画像内容')
}

async function handleSaveEdits() {
  if (!profile.value || savingEdits.value) return
  const edits: Record<string, string> = {}
  for (const [f, v] of Object.entries(editForm)) {
    const next = String(v).trim()
    const prev = String(fieldValue(profile.value, f) ?? '')
    if (next && next !== prev) edits[f] = next
  }
  if (!Object.keys(edits).length) {
    show('没有需要保存的修改')
    return
  }
  savingEdits.value = true
  try {
    profile.value = await saveProfile({
      edits,
      note: '画像页人工修订',
      expectedVersion: profile.value.profile_version,
    })
    for (const f of Object.keys(editTouched)) editTouched[f] = false
    fillEditForm(true)
    show('画像修改已保存为新版本（确认后用于智能匹配）')
  } catch (e) {
    show(e instanceof Error ? e.message : '画像修改保存失败')
  } finally {
    savingEdits.value = false
  }
}

// 确认当前画像：调用业务 API 保存修订并标记 confirmed
const confirming = ref(false)

async function handleConfirmProfile() {
  if (!profile.value || confirming.value) return
  confirming.value = true
  try {
    profile.value = await saveProfile({
      edits: {},
      confirm: true,
      expectedVersion: profile.value.profile_version,
    })
    show('画像已确认，可用于智能匹配')
  } catch (e) {
    show(e instanceof Error ? e.message : '画像确认失败')
  } finally {
    confirming.value = false
  }
}

// 版本历史：拉取历史版本并在版本卡片下展开
const versions = ref<ProfileRow[]>([])
const versionsOpen = ref(false)
const viewingVersion = ref<number | null>(null)

async function handleVersionHistory() {
  if (!versionsOpen.value) {
    try {
      versions.value = await listProfileVersions()
    } catch (e) {
      show(e instanceof Error ? e.message : '版本历史加载失败')
      return
    }
  }
  versionsOpen.value = !versionsOpen.value
}

// 查看某个历史版本的画像（只读预览，不影响当前编辑版本）
async function handleViewVersion(version: number) {
  if (viewingVersion.value === version) {
    profile.value = await getProfile()
    viewingVersion.value = null
    show('已返回当前版本')
    return
  }
  try {
    profile.value = await getProfileVersion(version)
    viewingVersion.value = version
    show(`正在预览 v${version}，再次点击可返回当前版本`)
  } catch (e) {
    show(e instanceof Error ? e.message : '版本加载失败')
  }
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <SideNav active-key="profile" />

    <main class="workspace">
      <!-- Hero -->
      <section class="hero">
        <div class="hero-content">
          <h1>{{ profileHeroCopy.title }}</h1>
          <p>{{ profileHeroCopy.subtitle }}</p>
        </div>
      </section>

      <!-- Top Section -->
      <section class="top-section">
        <!-- Basic Info -->
        <div class="basic-card">
          <img class="avatar" src="@/assets/art/avatar-student.png" alt="头像" />
          <div class="basic-info">
            <div class="name-row">
              <h2>{{ profileBasic.name }}</h2>
              <button class="edit-icon" type="button" @click="handleEdit('基本信息')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              </button>
              <span class="badge">✓ {{ profileBasic.status }}</span>
            </div>
            <div class="meta-row">
              <span>{{ profileBasic.gender }}</span>
              <span>{{ profileBasic.age }}</span>
              <span>{{ profileBasic.birth }}</span>
            </div>
            <div class="contact-row">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
              </svg>
              {{ profileBasic.phone }}
            </div>
            <div class="contact-row">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
              {{ profileBasic.email }}
            </div>
            <div class="contact-row">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
              {{ profileBasic.location }}
            </div>
          </div>
        </div>

        <!-- Radar Chart -->
        <div class="radar-card">
          <div class="card-header">
            <h3>能力雷达图</h3>
            <button class="help-btn" type="button" @click="handleDemo('帮助')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01" />
              </svg>
            </button>
            <div class="legend">
              <span><i class="dot primary" /> 我的能力</span>
              <span><i class="dot avg" /> 同届平均</span>
            </div>
          </div>
          <div class="radar-wrap">
            <svg viewBox="-32 -10 264 228">
              <g class="grid">
                <polygon
                  v-for="level in [25, 50, 75, 100]"
                  :key="level"
                  :points="radarData.dimensions.map((_, i) => {
                    const angle = (Math.PI * 2 * i) / radarData.dimensions.length - Math.PI / 2
                    const r = (level / 100) * 72
                    return `${100 + r * Math.cos(angle)},${100 + r * Math.sin(angle)}`
                  }).join(' ')"
                />
              </g>
              <polygon class="avg-shape" :points="radarAvgPoints.map((p) => `${p.x},${p.y}`).join(' ')" />
              <polygon class="primary-shape" :points="radarPoints.map((p) => `${p.x},${p.y}`).join(' ')" />
              <g class="labels">
                <text v-for="label in radarLabels" :key="label.text" :x="label.x" :y="label.y" class="dim-label">
                  {{ label.text }}
                  <tspan class="score">{{ label.score }}</tspan>
                </text>
              </g>
            </svg>
          </div>
        </div>

        <!-- Version Card -->
        <div class="version-card">
          <div class="version-header">
            <span>当前画像版本</span>
            <button class="link-btn" type="button" @click="handleVersionHistory">
              版本历史
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
          <div class="version-main">
            <div>
              <div class="version-number">
                {{ profileVersion.version }}
                <span class="badge-current">{{ profileVersion.status }}</span>
              </div>
              <div class="update-time">更新时间：{{ profileVersion.updateTime }}</div>
              <div class="version-desc">{{ profileVersion.desc }}</div>
            </div>
            <svg class="ai-illu" viewBox="0 0 80 80" fill="none">
              <rect x="15" y="10" width="50" height="60" rx="3" stroke="#a5b4fc" stroke-width="2" fill="#f0f4ff" />
              <path d="M25 25h30M25 35h30M25 45h20" stroke="#818cf8" stroke-width="2" stroke-linecap="round" />
              <circle cx="55" cy="55" r="12" fill="#6366f1" opacity="0.2" />
              <text x="48" y="59" fill="#4f46e5" font-size="12" font-weight="bold">AI</text>
            </svg>
          </div>
          <button class="btn-compare" type="button" @click="handleDemo('版本对比')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
            查看版本对比
          </button>
          <ul v-if="versionsOpen" class="version-list">
            <li v-for="v in versions" :key="v.id" class="version-item">
              <button
                type="button"
                class="version-link"
                :class="{ viewing: viewingVersion === v.profile_version }"
                @click="handleViewVersion(v.profile_version)"
              >
                v{{ v.profile_version }}{{ viewingVersion === v.profile_version ? '（预览中）' : '' }}
              </button>
              <span>{{ dateTime(v.created_at) }}</span>
              <span class="badge-current">{{ v.confirmed ? '已确认' : '待确认' }}</span>
            </li>
            <li v-if="!versions.length" class="version-item">暂无历史版本</li>
          </ul>
        </div>
      </section>

      <!-- Middle Section -->
      <section class="middle-section">
        <!-- Job Intention -->
        <div class="panel">
          <div class="panel-header">
            <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <circle cx="12" cy="12" r="3" />
            </svg>
            <h2>求职意向</h2>
            <button class="edit-btn" type="button" @click="handleEdit('求职意向')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              编辑
            </button>
          </div>
          <div class="intention-grid">
            <div class="intention-item">
              <span class="label">期望岗位</span>
              <span class="value">{{ jobIntention.targetPosition }}</span>
            </div>
            <div class="intention-item">
              <span class="label">期望行业</span>
              <span class="value">{{ jobIntention.industry }}</span>
            </div>
            <div class="intention-item">
              <span class="label">期望城市</span>
              <span class="value">{{ jobIntention.city }}</span>
            </div>
            <div class="intention-item">
              <span class="label">期望薪资</span>
              <span class="value">{{ jobIntention.salary }}</span>
            </div>
            <div class="intention-item">
              <span class="label">到岗时间</span>
              <span class="value">{{ jobIntention.entryTime }}</span>
            </div>
          </div>
        </div>

        <!-- Core Skills -->
        <div class="panel">
          <div class="panel-header">
            <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
            </svg>
            <h2>核心技能</h2>
            <button class="edit-btn" type="button" @click="handleEdit('核心技能')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
              编辑
            </button>
          </div>
          <div class="skills-grid">
            <span v-for="skill in coreSkills" :key="skill.name" class="skill-tag">
              {{ skill.name }}
              <button type="button" class="remove-btn" @click="handleDemo('移除技能')">×</button>
            </span>
            <button type="button" class="add-skill-btn" @click="handleDemo('添加技能')">
              + 添加技能
            </button>
          </div>
        </div>
      </section>

      <!-- Bottom Section -->
      <section class="bottom-section">
        <!-- Left Column -->
        <div class="left-col">
          <!-- Education -->
          <div class="panel">
            <div class="panel-header">
              <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
                <path d="M6 12v5c3 3 9 3 12 0v-5" />
              </svg>
              <h2>学历背景</h2>
              <button class="edit-btn" type="button" @click="handleEdit('学历背景')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
                编辑
              </button>
            </div>
            <div class="edu-card">
              <div class="edu-logo">🎓</div>
              <div class="edu-info">
                <h3>{{ education.school }}</h3>
                <div class="edu-meta">{{ education.period }}</div>
                <div class="edu-meta">{{ education.major }} {{ education.degree }}</div>
                <div class="edu-meta">GPA: {{ education.gpa }}（{{ education.ranking }}）</div>
              </div>
            </div>
          </div>

          <!-- Internship -->
          <div class="panel">
            <div class="panel-header">
              <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="7" width="20" height="14" rx="2" />
                <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
              </svg>
              <h2>实习经历</h2>
              <button class="link-btn" type="button" @click="handleDemo('查看更多')">
                查看更多
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
            <div v-for="item in internships" :key="item.id" class="experience-card">
              <div class="exp-header">
                <div>
                  <h3>{{ item.company }}</h3>
                  <div class="exp-position">{{ item.position }}</div>
                </div>
                <div class="exp-meta">
                  <div>{{ item.period }}</div>
                  <div>{{ item.location }}</div>
                </div>
              </div>
              <ul class="exp-highlights">
                <li v-for="(highlight, idx) in item.highlights" :key="idx">{{ highlight }}</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Right Column -->
        <div class="right-col">
          <!-- Projects -->
          <div class="panel">
            <div class="panel-header">
              <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
              <h2>项目经历</h2>
              <button class="link-btn" type="button" @click="handleDemo('查看更多')">
                查看更多
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
            <div v-for="item in projects" :key="item.id" class="experience-card">
              <div class="exp-header">
                <div>
                  <h3>{{ item.name }}</h3>
                  <div class="exp-position">{{ item.role }}</div>
                </div>
                <div class="exp-meta">
                  <div>{{ item.period }}</div>
                </div>
              </div>
              <ul class="exp-highlights">
                <li v-for="(highlight, idx) in item.highlights" :key="idx">{{ highlight }}</li>
              </ul>
            </div>
          </div>

          <!-- Evidence Sources -->
          <div class="panel">
            <div class="panel-header">
              <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 16v-4M12 8h.01" />
              </svg>
              <h2>证据来源</h2>
            </div>
            <div class="evidence-grid">
              <div v-for="source in evidenceSources" :key="source.type" class="evidence-item">
                <div class="evidence-percent">{{ source.percent }}</div>
                <div class="evidence-type">{{ source.type }}</div>
                <div class="evidence-desc">{{ source.desc }}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Bottom Bar -->
      <section class="bottom-bar">
        <div class="bar-header">
          <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
          <h2>编辑我的画像</h2>
          <span class="version-tag">当前编辑基于版本 {{ profileVersion.version }}</span>
          <div class="bar-actions">
            <button type="button" class="btn-cancel" @click="handleCancelEdit">取消</button>
            <button
              type="button"
              class="btn-outline"
              :disabled="savingEdits || !profile"
              @click="handleSaveEdits"
            >
              {{ savingEdits ? '保存中…' : '保存修改' }}
            </button>
            <button
              type="button"
              class="btn-confirm"
              :disabled="confirming || !profile"
              @click="handleConfirmProfile"
            >
              {{ confirming ? '确认中…' : '确认当前画像' }}
            </button>
          </div>
        </div>
        <div class="bar-content">
          <div class="bar-item">
            <h4>人工修订（可编辑字段）</h4>
            <div class="edit-grid">
              <label class="edit-field">
                <span>学历层次</span>
                <input v-model="editForm.education_level" placeholder="如：本科" @input="markEditTouched('education_level')" />
              </label>
              <label class="edit-field">
                <span>专业</span>
                <input v-model="editForm.major" placeholder="如：软件工程" @input="markEditTouched('major')" />
              </label>
              <label class="edit-field">
                <span>毕业年份</span>
                <input v-model="editForm.graduation_year" placeholder="如：2027" @input="markEditTouched('graduation_year')" />
              </label>
              <label class="edit-field">
                <span>求职意向</span>
                <input v-model="editForm.employment_intention" placeholder="如：后端开发工程师" @input="markEditTouched('employment_intention')" />
              </label>
              <label class="edit-field">
                <span>期望城市</span>
                <input v-model="editForm.preferred_cities" placeholder="如：杭州、上海" @input="markEditTouched('preferred_cities')" />
              </label>
              <label class="edit-field">
                <span>工作性质</span>
                <input v-model="editForm.employment_type" placeholder="如：全职" @input="markEditTouched('employment_type')" />
              </label>
            </div>
            <p class="edit-note">修改会保存为新的画像版本并保留原始抽取证据；点击「确认当前画像」后才用于智能匹配</p>
          </div>
          <div class="bar-item">
            <h4>自我介绍</h4>
            <p>{{ profileTags.selfIntro }}</p>
          </div>
          <div class="bar-item">
            <h4>优势特长</h4>
            <div class="tag-list">
              <span v-for="tag in profileTags.advantage" :key="tag" class="mini-tag">{{ tag }}</span>
              <button type="button" class="add-tag-btn">+ 添加标签</button>
            </div>
          </div>
          <div class="bar-item">
            <h4>职业发展期望</h4>
            <p>{{ profileTags.careerGoal }}</p>
          </div>
        </div>
      </section>
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

.hero {
  height: 138px;
  border-radius: 12px;
  position: relative;
  overflow: hidden;
  background: linear-gradient(110deg, #eff7ff 0%, #daeaff 47%, #b8d8ff 75%, #c1d3ff 100%);
  margin-bottom: 12px;
  padding: 0 37px;
  display: flex;
  align-items: center;
}
.hero-content {
  position: relative;
  z-index: 1;
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
  white-space: pre-line;
}

.top-section {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.basic-card {
  background: white;
  border: 1px solid #edf2f8;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  gap: 18px;
}
.avatar {
  width: 120px;
  height: 140px;
  object-fit: cover;
  border-radius: 8px;
}
.basic-info {
  flex: 1;
}
.name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.name-row h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
}
.edit-icon {
  border: 0;
  background: none;
  color: #2167f3;
  padding: 2px;
}
.edit-icon svg {
  width: 18px;
  height: 18px;
}
.badge {
  background: #d4f7e9;
  color: #03b58c;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  font-weight: 700;
}
.meta-row {
  display: flex;
  gap: 12px;
  color: #7b8aa9;
  font-size: 13px;
  margin-bottom: 12px;
}
.contact-row {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #7b8aa9;
  font-size: 13px;
  margin-bottom: 6px;
}
.contact-row svg {
  width: 16px;
  height: 16px;
}

.radar-card {
  background: white;
  border: 1px solid #edf2f8;
  border-radius: 12px;
  padding: 18px;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
}
.card-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
}
.help-btn {
  border: 0;
  background: none;
  color: #2167f3;
}
.help-btn svg {
  width: 18px;
  height: 18px;
}
.legend {
  margin-left: auto;
  display: flex;
  gap: 15px;
  font-size: 11px;
  color: #7b8aa9;
}
.legend span {
  display: flex;
  align-items: center;
  gap: 5px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.dot.primary {
  background: #2168ff;
}
.dot.avg {
  background: #a5b4fc;
}
.radar-wrap svg {
  width: 100%;
  height: auto;
}
.grid polygon {
  fill: none;
  stroke: #e5e7eb;
  stroke-width: 1;
}
.avg-shape {
  fill: #a5b4fc;
  opacity: 0.3;
  stroke: #a5b4fc;
  stroke-width: 1.5;
}
.primary-shape {
  fill: #2168ff;
  opacity: 0.35;
  stroke: #2168ff;
  stroke-width: 2;
}
.dim-label {
  font-size: 10px;
  fill: #4b5563;
  text-anchor: middle;
}
.score {
  font-size: 11px;
  font-weight: 700;
  fill: #1f2937;
}

.version-card {
  background: linear-gradient(135deg, #2168ff 0%, #6366f1 100%);
  border-radius: 12px;
  padding: 18px;
  color: white;
  display: flex;
  flex-direction: column;
}
.version-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}
.version-header span {
  font-size: 13px;
  opacity: 0.9;
}
.link-btn {
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.link-btn svg {
  width: 14px;
  height: 14px;
}
.version-main {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}
.version-number {
  font-size: 28px;
  font-weight: 800;
  display: flex;
  align-items: center;
  gap: 10px;
}
.badge-current {
  background: rgba(255, 255, 255, 0.2);
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
}
.update-time {
  font-size: 11px;
  opacity: 0.8;
  margin-top: 6px;
}
.version-desc {
  font-size: 11px;
  opacity: 0.85;
  margin-top: 8px;
  white-space: pre-line;
}
.version-list {
  list-style: none;
  margin-top: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.14);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.version-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
}
.version-item .badge-current {
  margin-left: auto;
}
.version-link {
  border: 0;
  background: none;
  color: inherit;
  font-size: 11px;
  padding: 0;
  cursor: pointer;
  text-decoration: underline;
}
.version-link.viewing {
  font-weight: 700;
}
.ai-illu {
  width: 80px;
  height: 80px;
  margin-left: auto;
}
.btn-compare {
  width: 100%;
  background: white;
  color: #2168ff;
  border: 0;
  border-radius: 8px;
  padding: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-weight: 700;
  margin-top: auto;
}
.btn-compare svg {
  width: 18px;
  height: 18px;
}

.middle-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.panel {
  background: white;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  padding: 18px;
}
.panel-header {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 15px;
}
.panel-header h2 {
  font-size: 17px;
  font-weight: 800;
  margin: 0;
  color: #101d46;
}
.header-icon {
  width: 24px;
  height: 24px;
  color: #176dff;
}
.edit-btn {
  margin-left: auto;
  border: 1px solid #2167f3;
  background: white;
  color: #2167f3;
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 5px;
}
.edit-btn svg {
  width: 14px;
  height: 14px;
}

.intention-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.intention-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.label {
  font-size: 12px;
  color: #8594ae;
}
.value {
  font-size: 13px;
  font-weight: 700;
  color: #1c2d55;
}

.skills-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.skill-tag {
  background: #eef3f8;
  color: #4b5563;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 6px;
}
.remove-btn {
  border: 0;
  background: none;
  color: #9ca3af;
  font-size: 14px;
  padding: 0;
}
.add-skill-btn {
  background: white;
  border: 1px dashed #d1d5db;
  color: #6b7280;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
}

.bottom-section {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 12px;
  margin-bottom: 12px;
}
.left-col,
.right-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edu-card {
  display: flex;
  gap: 15px;
}
.edu-logo {
  width: 60px;
  height: 60px;
  background: #eef3f8;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 32px;
}
.edu-info h3 {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 800;
}
.edu-meta {
  font-size: 12px;
  color: #7b8aa9;
  margin-bottom: 4px;
}

.experience-card {
  margin-bottom: 15px;
}
.experience-card:last-child {
  margin-bottom: 0;
}
.exp-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
}
.exp-header h3 {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 800;
}
.exp-position {
  font-size: 12px;
  color: #7b8aa9;
}
.exp-meta {
  font-size: 11px;
  color: #8594ae;
  text-align: right;
}
.exp-highlights {
  margin: 0;
  padding-left: 18px;
}
.exp-highlights li {
  font-size: 12px;
  color: #4b5563;
  line-height: 1.6;
  margin-bottom: 4px;
}

.evidence-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.evidence-item {
  background: #f8fafc;
  border-radius: 8px;
  padding: 15px;
  text-align: center;
}
.evidence-percent {
  font-size: 28px;
  font-weight: 800;
  color: #2168ff;
}
.evidence-type {
  font-size: 13px;
  font-weight: 700;
  color: #1c2d55;
  margin: 8px 0;
}
.evidence-desc {
  font-size: 11px;
  color: #8594ae;
  line-height: 1.5;
}

.bottom-bar {
  background: white;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  padding: 18px;
}
.bar-header {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 15px;
}
.bar-header h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 800;
}
.version-tag {
  background: #eef3f8;
  color: #6b7280;
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 4px;
}
.bar-actions {
  margin-left: auto;
  display: flex;
  gap: 10px;
}
.btn-cancel {
  border: 1px solid #d1d5db;
  background: white;
  color: #4b5563;
  border-radius: 6px;
  padding: 8px 20px;
  font-weight: 700;
}
.btn-confirm {
  border: 0;
  background: #2168ff;
  color: white;
  border-radius: 6px;
  padding: 8px 20px;
  font-weight: 700;
}
.bar-content {
  display: grid;
  grid-template-columns: 1.6fr 1fr 1fr 1fr;
  gap: 15px;
}
.bar-item h4 {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 800;
  color: #1c2d55;
}
.bar-item p {
  font-size: 12px;
  color: #4b5563;
  line-height: 1.6;
  margin: 0;
}
/* 人工修订表单（Phase5-3：真实保存为新画像版本） */
.edit-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.edit-field {
  display: grid;
  gap: 4px;
}
.edit-field span {
  font-size: 11px;
  font-weight: 700;
  color: #6b7280;
}
.edit-field input {
  border: 1px solid #d7e0f2;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  color: #1c2d55;
}
.edit-field input:focus {
  outline: 2px solid #c7d8f8;
  border-color: #9db9f0;
}
.edit-note {
  margin: 10px 0 0;
  font-size: 11px;
  color: #7686a8;
  line-height: 1.6;
}
.btn-outline {
  background: white;
  border: 1px solid #c9d6ef;
  color: #2168ff;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}
.btn-outline:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.mini-tag {
  background: #eef3f8;
  color: #4b5563;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
}
.add-tag-btn {
  background: white;
  border: 1px dashed #d1d5db;
  color: #6b7280;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 11px;
}

@media (max-width: 1190px) {
  .workspace {
    padding-right: 18px;
  }
  .top-section {
    grid-template-columns: 1fr 1fr;
  }
  .middle-section {
    grid-template-columns: 1fr;
  }
  .bottom-section {
    grid-template-columns: 1fr;
  }
  .bar-content {
    grid-template-columns: 1fr;
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
}
</style>
