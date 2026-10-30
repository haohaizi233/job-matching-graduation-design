/**
 * 工作台真实数据（单例缓存）。
 *
 * 顶栏与工作台共用同一份业务汇总，避免重复请求与请求竞态：
 *  - 同一时刻只允许一个在途请求（inflight 去重）；
 *  - 结果按 TTL 缓存，跨页面共享；
 *  - 401 不降级、不缓存，交由路由/认证层处理。
 */
import { ref } from 'vue'

import {
  buildRecommendJobs,
  buildSummary,
  fetchDashboardSource,
  type DashboardSummary,
} from '@/api/dashboard'
import { ApiError } from '@/api/http'
import { useAuth } from '@/composables/useAuth'
import type { JobItem } from '@/types'

const summary = ref<DashboardSummary | null>(null)
const recommendJobs = ref<JobItem[]>([])
const loading = ref(false)
const error = ref('')

let inflight: Promise<void> | null = null
let loadedAt = 0
const TTL_MS = 30_000

export function useDashboardSummary() {
  const { state } = useAuth()

  async function refresh(force = false): Promise<void> {
    if (!state.token) return
    if (!force && inflight) return inflight
    if (!force && summary.value && Date.now() - loadedAt < TTL_MS) return

    loading.value = true
    error.value = ''
    const username = state.user?.username ?? ''
    inflight = (async () => {
      try {
        const src = await fetchDashboardSource()
        summary.value = buildSummary(src, username)
        recommendJobs.value = await buildRecommendJobs(src)
        loadedAt = Date.now()
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          summary.value = null
          recommendJobs.value = []
          error.value = '登录状态已失效，请重新登录'
        } else {
          error.value = e instanceof ApiError ? e.message : '工作台数据加载失败，请重试'
        }
      } finally {
        loading.value = false
        inflight = null
      }
    })()
    return inflight
  }

  async function ensure(): Promise<void> {
    if (!summary.value || Date.now() - loadedAt >= TTL_MS) await refresh()
  }

  function reset(): void {
    summary.value = null
    recommendJobs.value = []
    loadedAt = 0
    error.value = ''
  }

  return {
    summary,
    recommendJobs,
    loading,
    error,
    refresh,
    ensure,
    reset,
  }
}
