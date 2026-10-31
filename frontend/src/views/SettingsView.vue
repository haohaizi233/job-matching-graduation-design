<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import { useToast } from '@/composables/useToast'
import {
  changePassword,
  getUserSettings,
  listSessions,
  revokeOtherSessions,
  revokeSession,
  saveUserSettings,
  SERVER_DEFAULT_SETTINGS,
} from '@/api/settings'
import { ApiError } from '@/api/http'
import {
  graduateYearOptions,
  heroCopy,
  notificationToggles,
  privacyToggles,
  regionOptions,
  resumeParseToggles,
  schoolYearOptions,
  securityItems,
  STORAGE_KEY,
  themeOptions,
} from '@/data/settings'
import type { SessionItem, UserSettings, UserSettingsPatch } from '@/types/settings'

import avatarSample from '@/assets/images/avatar/avatar-sample.png'
import bannerSettings from '@/assets/images/banner/banner-settings.png'

const { show } = useToast()

// ---------------------------------------------------------------- 加载状态
const loading = ref(true)
const loadError = ref('')
const saving = ref(false)

// ---------------------------------------------------------------- 表单状态
const form = reactive({ ...SERVER_DEFAULT_SETTINGS.basic })
const notifyState = reactive<Record<string, boolean>>(
  Object.fromEntries(notificationToggles.map((t) => [t.key, t.value])),
)
const parseState = reactive<Record<string, boolean>>(
  Object.fromEntries(resumeParseToggles.map((t) => [t.key, t.value])),
)
const privacyState = reactive<Record<string, boolean>>(
  Object.fromEntries(privacyToggles.map((t) => [t.key, t.value])),
)
const intentTags = ref<string[]>([...SERVER_DEFAULT_SETTINGS.job_intent.intentTags])
const newTag = ref('')
// 主题 = 纯客户端显示偏好（只存 localStorage，不上传服务端）
const theme = ref('light')
const savedHint = ref(false)

// ---------------------------------------------------------------- 密码修改
const showPwForm = ref(false)
const pwOld = ref('')
const pwNew = ref('')
const pwNew2 = ref('')
const pwBusy = ref(false)

// ---------------------------------------------------------------- 登录设备
const sessions = ref<SessionItem[]>([])
const sessionsError = ref('')

function applySettings(s: UserSettings) {
  Object.assign(form, s.basic)
  Object.assign(notifyState, { ...s.notifications })
  Object.assign(parseState, { ...s.resume_prefs })
  Object.assign(privacyState, { ...s.privacy })
  intentTags.value = [...(s.job_intent.intentTags ?? [])]
}

async function loadSessions() {
  try {
    sessions.value = await listSessions()
    sessionsError.value = ''
  } catch (e) {
    sessionsError.value = e instanceof ApiError ? e.message : '登录设备列表加载失败'
  }
}

async function loadAll() {
  loading.value = true
  loadError.value = ''
  try {
    applySettings(await getUserSettings())
    await loadSessions()
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : '设置加载失败，请重试'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const saved = JSON.parse(raw) as { theme?: string }
      if (saved.theme) theme.value = saved.theme
    }
  } catch {
    /* 浏览器禁用本地存储时静默降级 */
  }
  void loadAll()
})

function buildPatch(): UserSettingsPatch {
  return {
    basic: { ...form },
    notifications: {
      siteMessage: !!notifyState.siteMessage,
      emailNotice: !!notifyState.emailNotice,
      matchAlert: !!notifyState.matchAlert,
      weeklyReport: !!notifyState.weeklyReport,
    },
    resume_prefs: {
      autoParse: !!parseState.autoParse,
      ocrImages: !!parseState.ocrImages,
    },
    privacy: {
      publicResume: !!privacyState.publicResume,
      companyView: !!privacyState.companyView,
      hideSalary: !!privacyState.hideSalary,
    },
    job_intent: { intentTags: [...intentTags.value] },
  }
}

async function handleSave() {
  saving.value = true
  try {
    applySettings(await saveUserSettings(buildPatch()))
    try {
      // 主题仅本机保存
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ theme: theme.value }))
    } catch {
      /* 忽略 */
    }
    savedHint.value = true
    setTimeout(() => (savedHint.value = false), 2600)
    show('设置已保存到你的账号')
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      show('登录状态已失效，请重新登录')
    } else {
      show(e instanceof ApiError ? `保存失败：${e.message}` : '保存失败，请重试')
    }
  } finally {
    saving.value = false
  }
}

async function handleReset() {
  applySettings(SERVER_DEFAULT_SETTINGS)
  theme.value = 'light'
  await handleSave()
  show('已恢复默认设置')
}

function addTag() {
  const tag = newTag.value.trim()
  if (!tag) return
  if (intentTags.value.includes(tag)) {
    show('该标签已存在')
    return
  }
  intentTags.value = [...intentTags.value, tag]
  newTag.value = ''
}

function removeTag(tag: string) {
  intentTags.value = intentTags.value.filter((t) => t !== tag)
}

// ---------------------------------------------------------------- 密码修改
async function submitPassword() {
  if (!pwOld.value || !pwNew.value) {
    show('请填写原密码与新密码')
    return
  }
  if (pwNew.value !== pwNew2.value) {
    show('两次输入的新密码不一致')
    return
  }
  pwBusy.value = true
  try {
    const out = await changePassword(pwOld.value, pwNew.value)
    show(`密码已修改，其他 ${out.revoked_sessions} 个登录会话已退出`)
    pwOld.value = pwNew.value = pwNew2.value = ''
    showPwForm.value = false
    await loadSessions()
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      show('原密码不正确')
    } else if (e instanceof ApiError && e.status === 422) {
      show(`新密码不符合要求：${e.message}`)
    } else {
      show(e instanceof ApiError ? `修改失败：${e.message}` : '修改失败，请重试')
    }
  } finally {
    pwBusy.value = false
  }
}

function handleSecurity(item: { key: string; label: string; implemented: boolean }) {
  if (!item.implemented) {
    show(`「${item.label}」暂未接入后端安全服务，不可用`)
    return
  }
  if (item.key === 'password') {
    showPwForm.value = !showPwForm.value
  }
}

// ---------------------------------------------------------------- 登录设备
function uaLabel(ua: string): string {
  const s = (ua || '').trim()
  if (!s) return '未知设备'
  const browser = /Edg\//.test(s) ? 'Edge'
    : /Chrome\//.test(s) ? 'Chrome'
    : /Safari\//.test(s) && !/Chrome/.test(s) ? 'Safari'
    : /Firefox\//.test(s) ? 'Firefox'
    : '其他客户端'
  const os = /Windows/.test(s) ? 'Windows'
    : /iPhone|iPad|iOS/.test(s) ? 'iOS'
    : /Android/.test(s) ? 'Android'
    : /Mac OS/.test(s) ? 'macOS'
    : /Linux/.test(s) ? 'Linux'
    : '未知系统'
  return `${browser} · ${os}`
}

function formatTime(iso: string | null): string {
  if (!iso) return '时间未知'
  const d = new Date(String(iso).replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return String(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function handleOffline(sessionId: string) {
  try {
    await revokeSession(sessionId)
    show('该设备已退出登录')
    await loadSessions()
  } catch (e) {
    show(e instanceof ApiError ? `下线失败：${e.message}` : '下线失败，请重试')
    await loadSessions()
  }
}

async function handleOfflineOthers() {
  try {
    const n = await revokeOtherSessions()
    show(`已退出其他 ${n} 个登录会话`)
    await loadSessions()
  } catch (e) {
    show(e instanceof ApiError ? `操作失败：${e.message}` : '操作失败，请重试')
  }
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <SideNav active-key="settings" />

    <main class="workspace">
      <section class="hero" :style="{ backgroundImage: `url(${bannerSettings})` }">
        <div class="hero-content">
          <h1>{{ heroCopy.title }}</h1>
          <p v-for="(line, i) in heroCopy.lines" :key="i">{{ line }}</p>
        </div>
      </section>

      <div v-if="loading" class="state-banner">正在加载账号设置…</div>
      <div v-else-if="loadError" class="state-banner error">
        <span>{{ loadError }}</span>
        <button type="button" class="btn-outline" @click="loadAll">重试</button>
      </div>

      <section class="panel">
        <h2 class="panel-title">基本信息</h2>
        <div class="profile-row">
          <img class="avatar" :src="avatarSample" alt="头像" />
          <div class="field-grid">
            <label class="field">
              <span>昵称</span>
              <input v-model="form.nickname" />
            </label>
            <label class="field">
              <span>学校</span>
              <input v-model="form.school" />
            </label>
            <label class="field">
              <span>专业</span>
              <input v-model="form.major" />
            </label>
            <label class="field">
              <span>入学年份</span>
              <select v-model="form.enrollYear">
                <option v-for="opt in schoolYearOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </label>
            <label class="field">
              <span>毕业年份</span>
              <select v-model="form.graduateYear">
                <option v-for="opt in graduateYearOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </label>
            <label class="field">
              <span>所在地区</span>
              <select v-model="form.region">
                <option v-for="opt in regionOptions" :key="opt.value" :value="opt.label">{{ opt.label }}</option>
              </select>
            </label>
          </div>
        </div>
      </section>

      <div class="two-col">
        <section class="panel">
          <h2 class="panel-title">通知偏好</h2>
          <div v-for="item in notificationToggles" :key="item.key" class="toggle-row">
            <div>
              <strong>{{ item.label }}</strong>
              <span>{{ item.desc }}</span>
            </div>
            <button
              type="button"
              class="switch"
              :class="{ on: notifyState[item.key] }"
              role="switch"
              :aria-checked="notifyState[item.key]"
              @click="notifyState[item.key] = !notifyState[item.key]"
            >
              <i />
            </button>
          </div>
        </section>

        <section class="panel">
          <h2 class="panel-title">简历解析设置</h2>
          <div v-for="item in resumeParseToggles" :key="item.key" class="toggle-row">
            <div>
              <strong>{{ item.label }}</strong>
              <span>{{ item.desc }}</span>
            </div>
            <button
              type="button"
              class="switch"
              :class="{ on: parseState[item.key] }"
              role="switch"
              :aria-checked="parseState[item.key]"
              @click="parseState[item.key] = !parseState[item.key]"
            >
              <i />
            </button>
          </div>
          <h2 class="panel-title sub">主题与显示</h2>
          <p class="panel-note">主题仅保存在本机浏览器，不上传服务端</p>
          <div class="radio-row">
            <label v-for="opt in themeOptions" :key="opt.value" class="radio-item">
              <input v-model="theme" type="radio" :value="opt.value" />
              {{ opt.label }}
            </label>
          </div>
        </section>
      </div>

      <div class="two-col">
        <section class="panel">
          <h2 class="panel-title">密码与安全</h2>
          <div v-for="item in securityItems" :key="item.key" class="security-row">
            <div>
              <strong>
                {{ item.label }}
                <span v-if="!item.implemented" class="unavailable-badge">未接入</span>
              </strong>
              <span>{{ item.desc }}</span>
            </div>
            <button
              type="button"
              class="btn-outline"
              :disabled="!item.implemented"
              @click="handleSecurity(item)"
            >
              {{ item.key === 'password' && showPwForm ? '收起' : '修改' }}
            </button>
          </div>
          <div v-if="showPwForm" class="password-form">
            <label class="field">
              <span>原密码</span>
              <input v-model="pwOld" type="password" autocomplete="current-password" />
            </label>
            <label class="field">
              <span>新密码</span>
              <input
                v-model="pwNew"
                type="password"
                autocomplete="new-password"
                placeholder="至少 10 位，含字母与数字"
              />
            </label>
            <label class="field">
              <span>确认新密码</span>
              <input v-model="pwNew2" type="password" autocomplete="new-password" />
            </label>
            <button
              type="button"
              class="btn-primary"
              :disabled="pwBusy"
              @click="submitPassword"
            >
              {{ pwBusy ? '提交中…' : '确认修改密码' }}
            </button>
            <p class="panel-note">修改成功后，除当前设备外的所有登录会话将立即失效</p>
          </div>
        </section>

        <section class="panel">
          <h2 class="panel-title">隐私与数据权限</h2>
          <div v-for="item in privacyToggles" :key="item.key" class="toggle-row">
            <div>
              <strong>{{ item.label }}</strong>
              <span>{{ item.desc }}</span>
            </div>
            <button
              type="button"
              class="switch"
              :class="{ on: privacyState[item.key] }"
              role="switch"
              :aria-checked="privacyState[item.key]"
              @click="privacyState[item.key] = !privacyState[item.key]"
            >
              <i />
            </button>
          </div>
        </section>
      </div>

      <section class="panel">
        <h2 class="panel-title">推荐偏好</h2>
        <div class="tag-list">
          <span v-for="tag in intentTags" :key="tag" class="tag-chip">
            {{ tag }}
            <button type="button" aria-label="删除标签" @click="removeTag(tag)">×</button>
          </span>
        </div>
        <div class="tag-add">
          <input
            v-model="newTag"
            placeholder="输入新的求职意向标签，如：数据分析"
            @keyup.enter="addTag"
          />
          <button type="button" class="btn-outline" @click="addTag">添加标签</button>
        </div>
      </section>

      <div class="two-col">
        <section class="panel">
          <h2 class="panel-title">登录设备</h2>
          <p class="panel-note">来自真实服务端会话；下线后该设备的登录立即失效</p>
          <div v-if="sessionsError" class="state-banner error">
            <span>{{ sessionsError }}</span>
            <button type="button" class="btn-outline" @click="loadSessions">重试</button>
          </div>
          <div v-else-if="sessions.length === 0" class="empty-note">暂无活跃登录会话</div>
          <div v-for="s in sessions" :key="s.session_id" class="device-row">
            <div>
              <strong>
                {{ uaLabel(s.user_agent) }}
                <span v-if="s.current" class="current-badge">当前设备</span>
              </strong>
              <span>
                登录于 {{ formatTime(s.created_at) }}
                <template v-if="s.last_seen_at"> · 最近活动 {{ formatTime(s.last_seen_at) }}</template>
              </span>
            </div>
            <button
              v-if="!s.current"
              type="button"
              class="btn-outline"
              @click="handleOffline(s.session_id)"
            >
              下线
            </button>
          </div>
          <button
            v-if="sessions.filter((s) => !s.current).length > 0"
            type="button"
            class="btn-outline"
            @click="handleOfflineOthers"
          >
            下线其他全部设备
          </button>
        </section>

        <section class="panel">
          <h2 class="panel-title">账号安全日志</h2>
          <p class="panel-note">
            仅展示来自真实会话的登录记录；设置变更/改密等安全事件暂无审计存储，未接入
          </p>
          <div v-if="sessions.length === 0" class="empty-note">暂无登录记录</div>
          <div v-else class="log-list">
            <div v-for="s in sessions" :key="`log-${s.session_id}`" class="log-row">
              <i class="log-dot" />
              <div>
                <strong>账号登录成功</strong>
                <span>{{ formatTime(s.created_at) }} · {{ uaLabel(s.user_agent) }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="save-bar">
        <span v-if="savedHint" class="saved-hint">设置已保存</span>
        <button type="button" class="btn-ghost" :disabled="saving" @click="handleReset">恢复默认</button>
        <button type="button" class="btn-primary" :disabled="saving" @click="handleSave">
          {{ saving ? '保存中…' : '保存设置' }}
        </button>
      </div>
    </main>
  </div>
</template>

<style scoped>
.hero {
  height: 138px;
  border-radius: 12px;
  background-color: #daeaff;
  background-size: cover;
  background-position: center;
  margin-bottom: 12px;
  padding: 0 37px;
  display: flex;
  align-items: center;
}
.hero-content {
  background: rgba(255, 255, 255, 0.55);
  border-radius: 10px;
  padding: 12px 22px;
}
.hero-content h1 {
  font-size: 28px;
  margin: 0 0 6px;
  font-weight: 800;
  letter-spacing: -1px;
  color: #101d46;
}
.hero-content p {
  margin: 0;
  line-height: 1.7;
  color: #41567f;
  font-size: 13px;
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
.panel-title {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 800;
  color: #16234a;
}
.panel-title.sub {
  margin-top: 18px;
}

.two-col {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.two-col .panel {
  margin-bottom: 12px;
}

.profile-row {
  display: flex;
  gap: 22px;
  align-items: flex-start;
}
.avatar {
  width: 82px;
  height: 82px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
.field-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 13px 16px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field span {
  font-size: 12px;
  font-weight: 700;
  color: #4b5a7c;
}
.field input,
.field select {
  height: 38px;
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  padding: 0 11px;
  font-size: 12px;
  color: #243457;
  outline: 0;
  background: white;
}

.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 0;
  border-bottom: 1px solid #f0f3f9;
}
.toggle-row:last-child {
  border-bottom: 0;
}
.toggle-row strong {
  display: block;
  font-size: 13px;
  color: #16234a;
}
.toggle-row span {
  font-size: 11px;
  color: #8592ab;
}
.switch {
  width: 42px;
  height: 23px;
  border-radius: 12px;
  border: 0;
  background: #d5deeb;
  position: relative;
  flex-shrink: 0;
  transition: background 0.2s;
}
.switch i {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background: white;
  transition: left 0.2s;
}
.switch.on {
  background: #2168ff;
}
.switch.on i {
  left: 22px;
}
.radio-row {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
}
.radio-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #4b5a7c;
}
.radio-item input {
  accent-color: #2168ff;
}

.security-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 0;
  border-bottom: 1px solid #f0f3f9;
}
.security-row:last-child {
  border-bottom: 0;
}
.security-row strong {
  display: block;
  font-size: 13px;
  color: #16234a;
}
.security-row span {
  font-size: 11px;
  color: #8592ab;
}
.btn-outline {
  border: 1px solid #2168ff;
  background: white;
  color: #2168ff;
  border-radius: 6px;
  padding: 6px 15px;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.tag-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 13px;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #e8f1ff;
  color: #2168ff;
  border-radius: 14px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 700;
}
.tag-chip button {
  border: 0;
  background: none;
  color: #2168ff;
  font-size: 14px;
  padding: 0;
  line-height: 1;
}
.tag-add {
  display: flex;
  gap: 8px;
}
.tag-add input {
  flex: 1;
  max-width: 320px;
  height: 36px;
  border: 1px solid #d9e2ef;
  border-radius: 6px;
  padding: 0 11px;
  font-size: 12px;
  color: #243457;
  outline: 0;
}

.device-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 0;
  border-bottom: 1px solid #f0f3f9;
}
.device-row:last-child {
  border-bottom: 0;
}
.device-row strong {
  display: block;
  font-size: 13px;
  color: #16234a;
}
.device-row span {
  font-size: 11px;
  color: #8592ab;
}
.current-badge {
  display: inline-block;
  background: #e5f8f2;
  color: #03b58c;
  font-size: 10px;
  border-radius: 4px;
  padding: 2px 7px;
  margin-left: 6px;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.log-row {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 8px 0;
}
.log-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2168ff;
  margin-top: 5px;
  flex-shrink: 0;
}
.log-row strong {
  display: block;
  font-size: 12px;
  color: #16234a;
}
.log-row span {
  font-size: 11px;
  color: #8592ab;
}

.save-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 6px 0 20px;
}
.saved-hint {
  color: #03b58c;
  font-size: 12px;
  font-weight: 700;
  margin-right: auto;
}
.btn-ghost {
  height: 38px;
  padding: 0 20px;
  border: 1px solid #d9e2ef;
  background: white;
  color: #4b5a7c;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
}
.btn-primary {
  height: 38px;
  padding: 0 28px;
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
.btn-primary:disabled,
.btn-outline:disabled,
.btn-ghost:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ---- Phase5-3 / M2：加载 / 错误 / 空态与安全表单 ---- */
.state-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: #f3f7ff;
  border: 1px solid #dbe6fb;
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #33456e;
}
.state-banner.error {
  background: #fff3f2;
  border-color: #f2cfcb;
  color: #8c322b;
}
.panel-note {
  margin: -6px 0 12px;
  font-size: 12px;
  color: #7686a8;
  line-height: 1.6;
}
.empty-note {
  padding: 12px 0;
  font-size: 13px;
  color: #7686a8;
}
.unavailable-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #fff1e8;
  color: #b25a2b;
  font-size: 11px;
  font-weight: 700;
}
.password-form {
  margin-top: 12px;
  padding: 12px;
  border: 1px dashed #d7e0f2;
  border-radius: 10px;
  display: grid;
  gap: 10px;
}
.password-form .btn-primary {
  justify-self: start;
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
  .two-col {
    grid-template-columns: 1fr;
  }
  .field-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 540px) {
  .workspace {
    margin-left: 0;
    padding: 70px 10px 82px;
  }
  .profile-row {
    flex-direction: column;
  }
  .field-grid {
    grid-template-columns: 1fr;
  }
}
</style>
