import { expect, request as playwrightRequest, type Page } from '@playwright/test'

/**
 * Phase8-A / M9 浏览器 E2E 的 OAuth 专用助手（E13–E15）。
 *
 * 链路纪律（与 tests/e2e/serve_backend.py 一致）：
 *  - 真实 Vue + 真实 FastAPI + 真实 Alembic 迁移库，本站业务 API 不做任何 mock；
 *  - 只有「外部身份平台」被替换为本地模拟授权服务器（tests/e2e/fake_oauth_server.py），
 *    浏览器会真实跳转到模拟授权页并真实点击「同意授权 / 拒绝授权」；
 *  - 身份（subject）与异常行为由测试经 /control/* 注入，互不干扰。
 */

/** E2E 后端基址（playwright.config.ts 的 webServer：tests/e2e/serve_backend.py） */
export const BACKEND_URL = process.env.JM_E2E_BACKEND_URL || 'http://127.0.0.1:8123'

/** 模拟第三方授权服务器基址（tests/e2e/fake_oauth_server.py） */
export const FAKE_OAUTH_URL = process.env.JM_E2E_FAKE_OAUTH_URL || 'http://127.0.0.1:8125'

export type OAuthProviderId = 'wechat' | 'qq' | 'weibo'

/** 与前端 AuthCard / 后端 PROVIDER_LABELS 一致的按钮文案 */
export const PROVIDER_LABEL: Record<OAuthProviderId, string> = {
  wechat: '微信',
  qq: 'QQ',
  weibo: '微博',
}

export type FakeBehavior =
  | 'ok'
  | 'code_expired'
  | 'token_unavailable'
  | 'http_429'
  | 'http_500'
  | 'malformed'
  | 'identity_missing'
  | 'profile_fail'

/** 唯一第三方身份 subject（同一 subject 复用即验证「不重复建号」） */
export function uniqueSubject(prefix = 'e2e-sub'): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`
}

async function fakeControl(path: string, body?: unknown): Promise<void> {
  const ctx = await playwrightRequest.newContext({ baseURL: FAKE_OAUTH_URL })
  try {
    const res = body === undefined
      ? await ctx.post(path)
      : await ctx.post(path, { data: body })
    if (!res.ok()) {
      throw new Error(`模拟平台控制接口失败 ${path}：${res.status()} ${await res.text()}`)
    }
  } finally {
    await ctx.dispose()
  }
}

/** 注入下一次授权使用的第三方身份（subject 必须显式给定，避免用例互相污染） */
export async function setFakeIdentity(
  subject: string,
  displayName = '合成昵称',
): Promise<void> {
  await fakeControl('/control/identity', {
    subject,
    display_name: displayName,
    avatar_url: 'https://img.fake.test/a.png',
  })
}

/** 注入模拟平台异常行为（code 过期 / 429 / 500 / 响应异常 / 身份缺失 / 资料失败） */
export async function setFakeBehavior(behavior: FakeBehavior): Promise<void> {
  await fakeControl('/control/behavior', { behavior })
}

/** 复位模拟平台（每个用例开始前调用，保证互不干扰） */
export async function resetFakeProvider(): Promise<void> {
  await fakeControl('/control/reset')
}

/**
 * 记录主框架真实导航过的 URL（用于拿到 callback 地址 / 完成页地址做重放验证）。
 *
 * 同时记录两类事件：
 *  - framenavigated：已提交导航（含 Hash 片段，如 /#/oauth/complete?...）；
 *  - document 请求：302 中转 URL（如后端 /oauth/{provider}/callback?code&state）
 *    不会提交为帧导航，只在请求事件里可见，重放用例需要完整中转地址。
 */
export function recordNavigations(page: Page): string[] {
  const urls: string[] = []
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) urls.push(frame.url())
  })
  page.on('request', (req) => {
    if (req.resourceType() === 'document') urls.push(req.url())
  })
  return urls
}

/** 登录页点击某平台登录按钮，等待真实跳转到模拟授权页 */
export async function startOAuthFromLogin(
  page: Page,
  provider: OAuthProviderId,
): Promise<void> {
  await page.goto('/#/login')
  await page
    .getByRole('button', { name: `${PROVIDER_LABEL[provider]}登录` })
    .click()
  await expect(page).toHaveURL(/\/authorize\?/)
  await expect(page.getByTestId('fake-oauth-title')).toBeVisible()
}

/** 在模拟授权页点击「同意授权 / 拒绝授权」（真实点击、真实 302 回调） */
export async function decideConsent(page: Page, decision: 'allow' | 'deny'): Promise<void> {
  await page.getByTestId(decision === 'allow' ? 'fake-allow' : 'fake-deny').click()
}

/**
 * 完整第三方登录（登录页 -> 模拟授权页 -> 真实回调 -> 票据交换 -> 工作台）。
 * 返回全程真实导航 URL 列表（含 provider callback 地址，可用于重放用例）。
 */
export async function oauthLoginExpectDashboard(
  page: Page,
  provider: OAuthProviderId,
  subject: string,
): Promise<string[]> {
  const urls = recordNavigations(page)
  await setFakeIdentity(subject)
  await startOAuthFromLogin(page, provider)
  await decideConsent(page, 'allow')
  await expect(page).toHaveURL(/#\/dashboard/)
  await expect(page.locator('.user-menu-button')).toBeVisible()
  return urls
}

/** 当前登录用户名（用户菜单 strong 节点展示真实 username，不含副标题文案） */
export async function currentUsername(page: Page): Promise<string> {
  return (await page.locator('.user-menu-button strong').innerText()).trim()
}

/** 退出登录（真实撤销服务端会话） */
export async function logoutViaUi(page: Page): Promise<void> {
  await page.getByRole('button', { name: '个人账户菜单' }).click()
  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/#\/login/)
}

/** 从导航记录里取第一段「某前缀」的真实 URL（callback / complete 页地址） */
export function findNavigation(urls: string[], pattern: RegExp): string {
  return urls.find((u) => pattern.test(u)) || ''
}
