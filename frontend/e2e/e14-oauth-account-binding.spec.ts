import { expect, request as playwrightRequest, test } from '@playwright/test'

import {
  BASE_URL,
  STUDENT_PASSWORD,
  loginViaUi,
  registerAccount,
  toast,
  uniqueUsername,
} from './helpers'
import {
  BACKEND_URL,
  currentUsername,
  decideConsent,
  logoutViaUi,
  oauthLoginExpectDashboard,
  resetFakeProvider,
  setFakeIdentity,
  uniqueSubject,
} from './oauth-helpers'

/**
 * 设置页「第三方账号绑定」面板中的某平台绑定行（含「已绑定 / 未绑定」状态与绑定/解绑按钮）。
 * 限定在绑定面板内，避免与「登录设备」面板的 .device-row 混淆。
 */
function identityRow(page: import('@playwright/test').Page, label: string) {
  return page
    .locator('section.panel')
    .filter({ hasText: '第三方账号绑定' })
    .locator('.device-row')
    .filter({ hasText: label })
}

/** 绑定状态徽标（exact 匹配，防止命中「未绑定该平台账号」等说明文案） */
function identityBadge(
  page: import('@playwright/test').Page,
  label: string,
  state: '已绑定' | '未绑定',
) {
  return identityRow(page, label).getByText(state, { exact: true })
}

/** 纯 OAuth 用户「设置本站密码」表单（与「修改密码」表单同用 .password-form，需按文案区分） */
function setPwForm(page: import('@playwright/test').Page) {
  return page.locator('.password-form').filter({ hasText: '无需输入原密码' })
}

/**
 * E14 第三方账号绑定与解绑（真实 Vue + 真实 FastAPI；
 * 仅外部身份平台由本地模拟授权服务器替代）。
 */
test.describe('E14 第三方账号绑定与解绑', () => {
  test.beforeEach(async () => {
    await resetFakeProvider()
  })

  test('E14-1 已登录用户主动绑定 QQ → 设置页显示已绑定', async ({ page }) => {
    const username = uniqueUsername('e14bind')
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)
    await page.goto('/#/settings')

    await setFakeIdentity(uniqueSubject('e14qq'))
    const qqRow = identityRow(page, 'QQ')
    await expect(identityBadge(page, 'QQ', '未绑定')).toBeVisible()
    await qqRow.getByRole('button', { name: '绑定' }).click()

    await expect(page).toHaveURL(/\/authorize\?/)
    await decideConsent(page, 'allow')
    await expect(page).toHaveURL(/#\/settings/)
    await expect(identityBadge(page, 'QQ', '已绑定')).toBeVisible()
  })

  test('E14-2 第三方身份已被其他账号绑定 → 显式冲突且不静默转移', async ({ page }) => {
    const subject = uniqueSubject('e14conflict')

    // 用户 A 先绑定该第三方身份
    const userA = uniqueUsername('e14a')
    await registerAccount(BASE_URL, userA)
    await loginViaUi(page, userA)
    await page.goto('/#/settings')
    await setFakeIdentity(subject)
    await identityRow(page, 'QQ').getByRole('button', { name: '绑定' }).click()
    await decideConsent(page, 'allow')
    await expect(page).toHaveURL(/#\/settings/)
    await expect(identityBadge(page, 'QQ', '已绑定')).toBeVisible()
    await logoutViaUi(page)

    // 用户 B 尝试绑定同一第三方身份 -> 冲突
    const userB = uniqueUsername('e14b')
    await registerAccount(BASE_URL, userB)
    await loginViaUi(page, userB)
    await page.goto('/#/settings')
    await setFakeIdentity(subject)
    await identityRow(page, 'QQ').getByRole('button', { name: '绑定' }).click()
    await decideConsent(page, 'allow')

    await expect(page).toHaveURL(/#\/oauth\/complete/)
    await expect(page.locator('.oauth-complete .title')).toHaveText(
      '该第三方账号已绑定其他本站账号',
    )

    // 用户 B 的账号不被静默合并
    await page.goto('/#/settings')
    await expect(identityBadge(page, 'QQ', '未绑定')).toBeVisible()
  })

  test('E14-3 纯 OAuth 账号解绑唯一登录方式被拒绝（OAUTH_LAST_LOGIN_METHOD）', async ({ page }) => {
    await oauthLoginExpectDashboard(page, 'wechat', uniqueSubject('e14last'))

    await page.goto('/#/settings')
    const wxRow = identityRow(page, '微信')
    await expect(identityBadge(page, '微信', '已绑定')).toBeVisible()

    await wxRow.getByRole('button', { name: '解绑' }).click()
    await expect(toast(page)).toContainText('唯一登录方式')

    await page.goto('/#/settings')
    await expect(identityBadge(page, '微信', '已绑定')).toBeVisible()
  })

  test('E14-4 设置本站密码后可解绑第三方身份且密码登录可用', async ({ page }) => {
    await oauthLoginExpectDashboard(page, 'qq', uniqueSubject('e14pw'))
    const username = await currentUsername(page)

    await page.goto('/#/settings')
    await page.getByRole('button', { name: '设置本站密码' }).click()
    const form = setPwForm(page)
    await form.getByLabel('新密码', { exact: true }).fill(STUDENT_PASSWORD)
    await form.getByLabel('确认新密码', { exact: true }).fill(STUDENT_PASSWORD)
    const submitBtn = form.getByRole('button', { name: '确认设置密码' })
    // 页面是 scroll-behavior:smooth + 固定顶栏/侧栏，必须「瞬时」滚到视口中部再点，
    // 避免平滑滚动动画与 Playwright 滚动命中检查互相打架
    await submitBtn.evaluate((el) =>
      el.scrollIntoView({ block: 'center', behavior: 'instant' as ScrollBehavior }),
    )
    await submitBtn.click()
    await expect(toast(page)).toContainText('密码')

    const qqRow = identityRow(page, 'QQ')
    await qqRow.getByRole('button', { name: '解绑' }).click()
    await expect(toast(page)).toContainText('已解绑')
    await page.goto('/#/settings')
    await expect(identityBadge(page, 'QQ', '未绑定')).toBeVisible()

    // 账号未被锁死：退出后可用本站密码登录
    await logoutViaUi(page)
    await loginViaUi(page, username, STUDENT_PASSWORD)
    await expect(page).toHaveURL(/#\/dashboard/)
  })

  test('E14-5 未登录发起绑定被拒绝（OAUTH_BIND_REQUIRES_AUTH）', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BACKEND_URL })
    try {
      const res = await ctx.post('/api/v1/auth/oauth/start', {
        data: { provider: 'qq', mode: 'bind', return_path: '/settings' },
      })
      expect(res.status()).toBe(401)
      const body = (await res.json()) as { error?: { code?: string } }
      expect(body.error?.code).toBe('OAUTH_BIND_REQUIRES_AUTH')
    } finally {
      await ctx.dispose()
    }
  })
})
