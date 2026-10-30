<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import IconGlyph from '@/components/common/IconGlyph.vue'
import { useAuth } from '@/composables/useAuth'
import { useToast } from '@/composables/useToast'
import type { AuthMode } from '@/types'

import userIcon from '@/assets/icons/common/user-muted.png'
import lockIcon from '@/assets/icons/common/lock-muted.png'
import socialQq from '@/assets/icons/common/social-qq.png'
import socialWechat from '@/assets/icons/common/social-wechat.png'
import socialWeibo from '@/assets/icons/common/social-weibo.png'

const props = defineProps<{ mode: AuthMode }>()
const emit = defineEmits<{ (e: 'update:mode', mode: AuthMode): void }>()

const router = useRouter()
const route = useRoute()
const { show } = useToast()
const { login, register } = useAuth()

const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const remember = ref(true)
const passwordVisible = ref(false)
const confirmVisible = ref(false)
const formError = ref('')

const isRegister = computed(() => props.mode === 'register')
const isReset = computed(() => props.mode === 'reset')

const title = computed(() =>
  props.mode === 'login' ? '欢迎回来 👋' : props.mode === 'register' ? '创建你的账号 ✨' : '重置登录密码',
)
const description = computed(() =>
  props.mode === 'login'
    ? '登录你的账号，继续使用大学生就业岗位画像与简历智能匹配系统'
    : props.mode === 'register'
      ? '注册账号，开启你的智能简历分析与职业匹配之旅'
      : '请输入注册邮箱，后续可对接后端邮件验证流程',
)
const submitLabel = computed(() =>
  props.mode === 'login' ? '登 录' : props.mode === 'register' ? '注 册' : '发 送 重 置 邮 件',
)

function switchMode(mode: AuthMode) {
  formError.value = ''
  emit('update:mode', mode)
}

function togglePassword(target: 'password' | 'confirm') {
  if (target === 'password') {
    passwordVisible.value = !passwordVisible.value
  } else {
    confirmVisible.value = !confirmVisible.value
  }
}

const emailPattern = /^\S+@\S+\.\S+$/

const submitting = ref(false)

async function handleSubmit() {
  let error = ''
  if (props.mode === 'reset') {
    if (!emailPattern.test(email.value.trim())) error = '请输入有效的邮箱地址'
  } else {
    if (username.value.trim().length < 2) error = '请输入至少2个字符的用户名或邮箱'
    else if (!password.value) error = '请输入密码'
    else if (isRegister.value) {
      if (!emailPattern.test(email.value.trim())) error = '请输入有效的邮箱地址'
      else if (password.value.length < 8) error = '密码至少需要8位字符'
      else if (password.value !== confirmPassword.value) error = '两次输入的密码不一致'
    }
  }
  formError.value = error
  if (error) return

  if (props.mode === 'reset') {
    show('重置邮件为 UI 演示，请连接后端邮件服务', 'top')
    return
  }

  submitting.value = true
  try {
    if (props.mode === 'login') {
      await login(username.value.trim(), password.value)
      show('登录成功，正在进入工作台...', 'top', 1600)
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
      setTimeout(() => router.push(redirect || '/dashboard'), 400)
    } else {
      await register(username.value.trim(), password.value, email.value.trim())
      show('注册成功，请登录', 'top')
      switchMode('login')
    }
  } catch (e) {
    formError.value = e instanceof Error ? e.message : '请求失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

const socials = [
  { key: 'QQ', label: 'QQ', icon: socialQq },
  { key: '微信', label: '微信', icon: socialWechat },
  { key: '微博', label: '微博', icon: socialWeibo },
]

function handleSocial(provider: string) {
  show(`${provider}第三方登录为 UI 演示，尚未接入 OAuth 授权`, 'top')
}
</script>

<template>
  <section class="auth-card" :class="{ 'auth-register': isRegister, 'auth-reset': isReset }" aria-label="账号登录与注册">
    <div class="tabs" role="tablist" aria-label="登录注册">
      <button type="button" class="tab" role="tab" :aria-selected="!isRegister" @click="switchMode('login')">登录</button>
      <button type="button" class="tab" role="tab" :aria-selected="isRegister" @click="switchMode('register')">注册</button>
    </div>

    <div class="auth-content">
      <h2 class="welcome">{{ title }}</h2>
      <p class="welcome-desc">{{ description }}</p>

      <form novalidate @submit.prevent="handleSubmit">
        <div v-show="!isReset" class="input-group">
          <label for="username">用户名 / 邮箱</label>
          <div class="input-shell">
            <img class="prefix" :src="userIcon" alt="" aria-hidden="true" />
            <input
              id="username"
              v-model="username"
              name="username"
              autocomplete="username"
              placeholder="请输入用户名或邮箱"
              required
            />
          </div>
        </div>

        <div v-show="isRegister || isReset" class="input-group">
          <label for="email">电子邮箱</label>
          <div class="input-shell">
            <img class="prefix" :src="userIcon" alt="" aria-hidden="true" />
            <input id="email" v-model="email" name="email" type="email" autocomplete="email" placeholder="请输入有效电子邮箱" />
          </div>
        </div>

        <div v-show="!isReset" class="input-group">
          <label for="password">密码</label>
          <div class="input-shell">
            <img class="prefix" :src="lockIcon" alt="" aria-hidden="true" />
            <input
              id="password"
              v-model="password"
              name="password"
              :type="passwordVisible ? 'text' : 'password'"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
              placeholder="请输入密码"
              required
            />
            <button
              class="eye-toggle"
              type="button"
              :aria-label="passwordVisible ? '隐藏密码' : '显示密码'"
              @click="togglePassword('password')"
            >
              <IconGlyph :name="passwordVisible ? 'eye' : 'eyeOff'" />
            </button>
          </div>
        </div>

        <div v-show="isRegister" class="input-group">
          <label for="confirmPassword">确认密码</label>
          <div class="input-shell">
            <img class="prefix" :src="lockIcon" alt="" aria-hidden="true" />
            <input
              id="confirmPassword"
              v-model="confirmPassword"
              name="confirmPassword"
              :type="confirmVisible ? 'text' : 'password'"
              autocomplete="new-password"
              placeholder="请再次输入密码"
            />
            <button
              class="eye-toggle"
              type="button"
              :aria-label="confirmVisible ? '隐藏密码' : '显示密码'"
              @click="togglePassword('confirm')"
            >
              <IconGlyph :name="confirmVisible ? 'eye' : 'eyeOff'" />
            </button>
          </div>
        </div>

        <div v-show="props.mode === 'login'" class="form-meta">
          <label class="remember">
            <input v-model="remember" type="checkbox" />记住我
          </label>
          <button type="button" class="text-link" @click="switchMode('reset')">忘记密码?</button>
        </div>

        <p class="form-errors" role="alert">{{ formError }}</p>

        <button class="submit-button" type="submit" :disabled="submitting">
          <span>{{ submitting ? '提交中...' : submitLabel }}</span>
          <span class="submit-arrow"><IconGlyph name="arrow" /></span>
        </button>
      </form>

      <div v-show="props.mode === 'login'" class="other-methods">或使用以下方式登录</div>
      <div v-show="props.mode === 'login'" class="socials">
        <button
          v-for="social in socials"
          :key="social.key"
          type="button"
          class="social-button"
          :aria-label="`${social.label}登录`"
          @click="handleSocial(social.key)"
        >
          <img :src="social.icon" alt="" />
          <span>{{ social.label }}</span>
        </button>
      </div>

      <aside class="notice">
        <IconGlyph name="info" class="notice-icon" />
        <p>系统提供的岗位匹配评分仅基于你的简历画像与岗位要求的相似度计算，仅供参考，不代表企业的实际录用概率。</p>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.auth-card {
  position: absolute;
  top: 43px;
  right: 5.7%;
  width: 514px;
  min-height: 857px;
  background: rgba(255, 255, 255, 0.97);
  border: 1px solid rgba(230, 236, 248, 0.7);
  border-radius: 19px;
  box-shadow: 0 11px 38px rgba(69, 107, 172, 0.09);
  padding: 42px 44px 27px;
  z-index: 2;
}
.tabs {
  display: flex;
  height: 50px;
  border-bottom: 2px solid #e6ebf4;
  gap: 0;
}
.tab {
  flex: 1;
  border: 0;
  background: transparent;
  position: relative;
  padding: 0 0 15px;
  color: #596885;
  font-size: 24px;
  font-weight: 800;
  transition: 0.18s;
}
.tab[aria-selected='true'] {
  color: #2073ff;
}
.tab[aria-selected='true']::after {
  content: '';
  position: absolute;
  bottom: -2px;
  height: 3px;
  width: 64px;
  left: 50%;
  transform: translateX(-50%);
  background: #2f78ff;
  border-radius: 5px;
}
.auth-content {
  padding-top: 36px;
}
.welcome {
  font-size: 28px;
  font-weight: 900;
  margin: 0 0 9px;
  line-height: 1.35;
  letter-spacing: 0.2px;
  color: #0c1b40;
}
.welcome-desc {
  font-size: 15.5px;
  line-height: 1.8;
  color: #77859e;
  letter-spacing: 0.1px;
  margin: 0 0 27px;
  font-weight: 500;
}
.input-group {
  margin-bottom: 20px;
}
.input-group label {
  display: block;
  margin-bottom: 11px;
  font-weight: 800;
  font-size: 16px;
  color: #162347;
}
.input-shell {
  display: flex;
  align-items: center;
  border: 1.5px solid #dbe3ee;
  border-radius: 9px;
  background: #fff;
  height: 54px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.input-shell:focus-within {
  border-color: #5894ff;
  box-shadow: 0 0 0 3px #2f79ff17;
}
.input-shell .prefix {
  width: 19px;
  height: 19px;
  margin-left: 20px;
  object-fit: contain;
  flex-shrink: 0;
}
.input-shell input {
  flex: 1;
  outline: 0;
  border: 0;
  color: #17254b;
  background: none;
  min-width: 0;
  font-size: 15.5px;
  padding: 0 14px;
}
.input-shell input::placeholder {
  color: #a4afc2;
}
.input-shell .eye-toggle {
  display: grid;
  place-items: center;
  width: 47px;
  height: 100%;
  border: 0;
  background: none;
  color: #8b98af;
}
.input-shell .eye-toggle:hover {
  color: #2c6fff;
}
.input-shell .eye-toggle .glyph {
  height: 21px;
  width: 21px;
  stroke-width: 1.9;
}
.form-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 10px 0 14px;
}
.remember {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 16px;
  color: #253553;
  cursor: pointer;
}
.remember input {
  accent-color: #3478ff;
  width: 20px;
  height: 20px;
  margin: 0;
  cursor: pointer;
}
.text-link {
  border: 0;
  padding: 0;
  background: none;
  color: #2476ff;
  font-size: 15px;
  font-weight: 700;
}
.text-link:hover {
  text-decoration: underline;
}
.form-errors {
  display: none;
  color: #db435b;
  font-size: 13px;
  line-height: 1.5;
  margin: 0 0 12px;
}
.form-errors:not(:empty) {
  display: block;
}
.submit-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 60px;
  position: relative;
  border: 0;
  border-radius: 10px;
  background: linear-gradient(100deg, #3074ff, #5269ff 63%, #6259fa);
  color: white;
  font-weight: 800;
  font-size: 20px;
  letter-spacing: 3px;
  box-shadow: 0 7px 15px rgba(37, 92, 255, 0.14);
  transition: filter 0.2s, transform 0.15s;
}
.submit-button:hover {
  filter: brightness(1.04);
  transform: translateY(-1px);
}
.submit-button:active {
  transform: none;
}
.submit-arrow {
  position: absolute;
  right: 17px;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: #fff;
  color: #4d73ff;
  display: grid;
  place-items: center;
}
.submit-arrow .glyph {
  width: 22px;
  height: 22px;
}
.other-methods {
  margin-top: 31px;
  display: flex;
  align-items: center;
  gap: 17px;
  color: #a2acbf;
  font-size: 14px;
  white-space: nowrap;
}
.other-methods::before,
.other-methods::after {
  content: '';
  height: 1px;
  background: #e0e8f3;
  flex: 1;
}
.socials {
  display: flex;
  justify-content: space-around;
  gap: 18px;
  margin-top: 23px;
  padding: 0 0 0 76px;
}
.social-button {
  background: none;
  border: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: #71809a;
  font-size: 14px;
  padding: 0;
  min-width: 65px;
}
.social-button img {
  width: 60px;
  height: 60px;
  object-fit: contain;
  transition: transform 0.2s;
}
.social-button:hover img {
  transform: translateY(-3px);
}
.notice {
  margin-top: 27px;
  min-height: 69px;
  border: 1px solid #d9e6ff;
  background: linear-gradient(90deg, #f0f5ff, #f4f7ff);
  border-radius: 10px;
  padding: 14px 15px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.notice .notice-icon {
  width: 19px;
  height: 19px;
  flex-shrink: 0;
  color: #2576ff;
}
.notice p {
  margin: 0;
  color: #7a88a5;
  font-size: 12.5px;
  line-height: 1.65;
}

/* 注册 / 找回密码模式的排版差异 */
.auth-register .welcome-desc {
  margin-bottom: 19px;
}
.auth-register .input-group {
  margin-bottom: 13px;
}
.auth-register .notice {
  margin-top: 24px;
}
.auth-reset .welcome-desc {
  margin-bottom: 30px;
}
.auth-reset .notice {
  margin-top: 100px;
}

@media (max-width: 1150px) {
  .auth-card {
    right: 3%;
    width: 470px;
    padding: 36px 32px;
  }
}
@media (max-width: 900px) {
  .auth-card {
    position: relative;
    top: auto;
    right: auto;
    align-self: center;
    width: min(94%, 514px);
    min-height: auto;
    margin: 35px 0 0;
    padding: 35px;
  }
}
@media (max-width: 520px) {
  .auth-card {
    padding: 25px 20px;
    margin-top: 24px;
  }
  .tab {
    font-size: 20px;
  }
  .auth-content {
    padding-top: 27px;
  }
  .welcome {
    font-size: 24px;
  }
  .welcome-desc {
    font-size: 13px;
  }
  .socials {
    padding: 0 10px;
  }
  .notice p {
    font-size: 11.5px;
  }
}
</style>
