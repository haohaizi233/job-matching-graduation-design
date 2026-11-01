<script setup lang="ts">
/**
 * OAuth 授权完成页（/#/oauth/complete）。
 *
 * 后端 callback 302 到这里时只携带**非秘密**参数（rid/mode/status/reason/return_path），
 * 一次性票据在 HttpOnly Cookie 中（按事务 rid 隔离），由本页 POST /auth/oauth/exchange
 * 换取本站会话。页面职责：
 *   - 识别授权结果（ok / error）并自动发起票据交换（防重复提交：交换只跑一次）；
 *   - login 模式：写入 useAuth 登录态并跳转原目标页；
 *   - bind 模式：展示绑定结果并跳回个人设置；
 *   - 处理授权取消（OAUTH_ACCESS_DENIED）、票据过期/已消费、刷新页面等；
 *   - 全程不显示任何第三方 Token / code / state。
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { useAuth } from '@/composables/useAuth'
import { useOAuth } from '@/composables/useOAuth'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const { applyLoginResult } = useAuth()
const { exchange } = useOAuth()
const { show } = useToast()

const phase = ref<'working' | 'done' | 'error'>('working')
const message = ref('正在完成第三方登录...')
const detail = ref('')
const consumed = ref(false)

/** 允许的站内回跳目标（与后端 return_path 白名单口径一致） */
function safeReturnPath(raw: unknown, fallback: string): string {
  const path = typeof raw === 'string' ? raw : ''
  const allowed = ['/dashboard', '/resume', '/profile', '/jobs', '/job/', '/matching',
                   '/history', '/feedback', '/settings']
  if (path && path.startsWith('/') && !path.startsWith('//') && !path.includes('\\') &&
      allowed.some((p) => path === p.replace(/\/$/, '') || path.startsWith(p))) {
    return path
  }
  return fallback
}

function fail(msg: string, reason: string) {
  phase.value = 'error'
  message.value = msg
  detail.value = reason
}

onMounted(async () => {
  // 防重复提交：同一页面实例只允许一次交换（刷新后票据已被消费则走明确错误提示）
  if (consumed.value) return
  consumed.value = true

  const q = route.query
  const rid = typeof q.rid === 'string' ? q.rid : ''
  const mode = q.mode === 'bind' ? 'bind' : 'login'
  const status = q.status === 'error' ? 'error' : 'ok'
  const reason = typeof q.reason === 'string' ? q.reason : ''
  const returnPath = safeReturnPath(q.return_path, mode === 'bind' ? '/settings' : '/dashboard')

  if (status === 'error') {
    if (reason === 'OAUTH_ACCESS_DENIED') {
      fail('你已取消第三方授权', 'OAUTH_ACCESS_DENIED')
    } else if (reason === 'OAUTH_TICKET_ALREADY_USED') {
      fail('本次登录凭证已被使用，请重新发起登录', 'OAUTH_TICKET_ALREADY_USED')
    } else {
      fail('第三方登录未完成，请重试', reason || 'UNKNOWN')
    }
    return
  }

  if (!rid) {
    fail('缺少事务标识，无法完成登录', 'MISSING_RID')
    return
  }

  try {
    const out = await exchange(rid)
    if (out.mode === 'login') {
      applyLoginResult(out.result)
      phase.value = 'done'
      message.value = '登录成功，正在进入...'
      show('第三方登录成功', 'top', 1400)
      setTimeout(() => router.replace(returnPath), 400)
      return
    }
    // bind 模式
    phase.value = 'done'
    message.value = out.already_bound ? '该第三方账号此前已绑定，无需重复绑定' : '第三方账号绑定成功'
    show(message.value, 'top', 1600)
    setTimeout(() => router.replace('/settings'), 500)
  } catch (e) {
    if (e instanceof ApiError) {
      const map: Record<string, string> = {
        OAUTH_TICKET_EXPIRED: '登录凭证已过期，请重新发起第三方登录',
        OAUTH_TICKET_ALREADY_USED: '登录凭证已被使用，请重新发起第三方登录',
        OAUTH_SESSION_CHANGED: '登录状态已变化，绑定已取消，请重新登录后再绑定',
        OAUTH_BIND_REQUIRES_AUTH: '绑定需要先登录本站账号',
        OAUTH_IDENTITY_CONFLICT: '该第三方账号已绑定其他本站账号',
        OAUTH_INVALID_REDIRECT: '请求来源不被信任，操作已取消',
      }
      fail(map[e.code] || '第三方登录未完成，请重试', e.code)
    } else {
      fail('网络异常，第三方登录未完成', 'NETWORK_ERROR')
    }
  }
})
</script>

<template>
  <section class="oauth-complete" aria-label="第三方登录结果">
    <div class="card">
      <div v-if="phase === 'working'" class="spinner" aria-hidden="true"></div>
      <div v-else-if="phase === 'done'" class="badge ok" aria-hidden="true">✓</div>
      <div v-else class="badge err" aria-hidden="true">!</div>

      <h1 class="title">{{ message }}</h1>
      <p v-if="detail" class="detail">{{ detail }}</p>

      <div class="actions">
        <button
          v-if="phase === 'error'"
          type="button"
          class="primary"
          @click="router.replace('/login')"
        >
          返回登录
        </button>
        <button
          v-if="phase === 'error'"
          type="button"
          class="ghost"
          @click="router.replace('/dashboard')"
        >
          回到首页
        </button>
      </div>

      <p class="hint">本页不会显示任何第三方平台令牌或授权码。</p>
    </div>
  </section>
</template>

<style scoped>
.oauth-complete {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: linear-gradient(160deg, #eef3ff, #f7f9ff);
  padding: 24px;
}
.card {
  width: min(420px, 92vw);
  background: #fff;
  border: 1px solid #e3eaf6;
  border-radius: 16px;
  box-shadow: 0 12px 36px rgba(50, 90, 180, 0.1);
  padding: 42px 34px;
  text-align: center;
}
.spinner {
  width: 42px;
  height: 42px;
  margin: 0 auto 22px;
  border: 4px solid #dfe7f7;
  border-top-color: #2f78ff;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.badge {
  width: 52px;
  height: 52px;
  margin: 0 auto 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 26px;
  font-weight: 800;
  color: #fff;
}
.badge.ok {
  background: #2fbf71;
}
.badge.err {
  background: #e2556b;
}
.title {
  font-size: 20px;
  font-weight: 800;
  color: #12234a;
  margin: 0 0 10px;
  line-height: 1.5;
}
.detail {
  font-size: 13px;
  color: #8a97ae;
  margin: 0 0 8px;
}
.actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin: 22px 0 6px;
}
.primary,
.ghost {
  border: 0;
  border-radius: 9px;
  padding: 11px 22px;
  font-size: 14.5px;
  font-weight: 700;
  cursor: pointer;
}
.primary {
  background: linear-gradient(100deg, #3074ff, #5269ff);
  color: #fff;
}
.ghost {
  background: #eef2fb;
  color: #45577c;
}
.hint {
  margin: 18px 0 0;
  font-size: 12px;
  color: #a4afc2;
}
</style>
