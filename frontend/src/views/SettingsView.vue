<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'
import { useToast } from '@/composables/useToast'
import {
  defaultSettings,
  deviceList,
  graduateYearOptions,
  heroCopy,
  notificationToggles,
  privacyToggles,
  regionOptions,
  resumeParseToggles,
  schoolYearOptions,
  securityItems,
  securityLogs,
  STORAGE_KEY,
  themeOptions,
} from '@/data/settings'

import avatarSample from '@/assets/images/avatar/avatar-sample.png'
import bannerSettings from '@/assets/images/banner/banner-settings.png'

const { show } = useToast()

const form = reactive({ ...defaultSettings })
const notifyState = reactive<Record<string, boolean>>(
  Object.fromEntries(notificationToggles.map((t) => [t.key, t.value])),
)
const parseState = reactive<Record<string, boolean>>(
  Object.fromEntries(resumeParseToggles.map((t) => [t.key, t.value])),
)
const privacyState = reactive<Record<string, boolean>>(
  Object.fromEntries(privacyToggles.map((t) => [t.key, t.value])),
)
const intentTags = ref([...defaultSettings.intentTags])
const newTag = ref('')
const devices = ref(deviceList.map((d) => ({ ...d })))
const savedHint = ref(false)

onMounted(() => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const saved = JSON.parse(raw) as Partial<typeof defaultSettings> & { intentTags?: string[] }
      Object.assign(form, saved)
      if (Array.isArray(saved.intentTags)) intentTags.value = [...saved.intentTags]
    }
  } catch {
    /* 浏览器禁用本地存储时静默降级 */
  }
})

function handleSave() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...form, intentTags: intentTags.value }),
    )
    savedHint.value = true
    setTimeout(() => (savedHint.value = false), 2600)
    show('设置已保存到当前浏览器（演示）')
  } catch {
    show('当前浏览器禁用了本地存储，设置仅本次生效')
  }
}

function handleReset() {
  Object.assign(form, defaultSettings)
  intentTags.value = [...defaultSettings.intentTags]
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* 忽略 */
  }
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

function handleSecurity(item: { label: string }) {
  show(`「${item.label}」演示：表单校验已模拟，未接入账号服务`)
}

function handleOffline(id: number) {
  devices.value = devices.value.filter((d) => d.id !== id)
  show('该设备已下线（演示）')
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
          <div class="radio-row">
            <label v-for="opt in themeOptions" :key="opt.value" class="radio-item">
              <input v-model="form.theme" type="radio" :value="opt.value" />
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
              <strong>{{ item.label }}</strong>
              <span>{{ item.desc }}</span>
            </div>
            <button type="button" class="btn-outline" @click="handleSecurity(item)">修改</button>
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
          <div v-for="device in devices" :key="device.id" class="device-row">
            <div>
              <strong>
                {{ device.name }}
                <span v-if="device.current" class="current-badge">当前设备</span>
              </strong>
              <span>{{ device.place }} · {{ device.time }}</span>
            </div>
            <button
              v-if="!device.current"
              type="button"
              class="btn-outline"
              @click="handleOffline(device.id)"
            >
              下线
            </button>
          </div>
        </section>

        <section class="panel">
          <h2 class="panel-title">账号安全日志</h2>
          <div class="log-list">
            <div v-for="log in securityLogs" :key="log.id" class="log-row">
              <i class="log-dot" />
              <div>
                <strong>{{ log.event }}</strong>
                <span>{{ log.time }} · {{ log.location }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="save-bar">
        <span v-if="savedHint" class="saved-hint">设置已保存</span>
        <button type="button" class="btn-ghost" @click="handleReset">恢复默认</button>
        <button type="button" class="btn-primary" @click="handleSave">保存设置</button>
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
