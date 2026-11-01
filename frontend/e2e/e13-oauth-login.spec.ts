import { expect, test } from '@playwright/test'

import { toast } from './helpers'
import {
  currentUsername,
  decideConsent,
  logoutViaUi,
  oauthLoginExpectDashboard,
  recordNavigations,
  resetFakeProvider,
  setFakeBehavior,
  setFakeIdentity,
  startOAuthFromLogin,
  uniqueSubject,
} from './oauth-helpers'

/**
 * E13 第三方 OAuth 登录（真实 Vue + 真实 FastAPI + 隔离测试库；
 * 仅外部身份平台由 tests/e2e/fake_oauth_server.py 模拟，本站业务 API 不 mock）。
 */
test.describe('E13 第三方 OAuth 登录', () => {
  test.beforeEach(async () => {
    await resetFakeProvider()
  })

  test('E13-1 微信扫码授权登录 → 进入工作台且登录态真实生效', async ({ page }) => {
    const subject = uniqueSubject('e13wechat')

    await test.step('E13-1a 登录页点击微信登录，真实跳转到授权页', async () => {
      await setFakeIdentity(subject)
      await startOAuthFromLogin(page, 'wechat')
    })

    await test.step('E13-1b 同意授权后真实回调并完成票据交换', async () => {
      await decideConsent(page, 'allow')
      await expect(page).toHaveURL(/#\/dashboard/)
    })

    await test.step('E13-1c 工作台展示 OAuth 创建的本站用户名（非昵称）', async () => {
      const username = await currentUsername(page)
      expect(username).toMatch(/^wechat_[0-9a-f]{8}$/)
      await expect(toast(page)).toContainText('第三方登录成功')
    })

    await test.step('E13-1d 登录态真实可用：可进入需鉴权业务页', async () => {
      await page.goto('/#/resume')
      await expect(page).toHaveURL(/#\/resume/)
      await expect(page.locator('.user-menu-button')).toBeVisible()
    })
  })

  test('E13-2 同一第三方身份重复登录不创建重复本地账号', async ({ page }) => {
    const subject = uniqueSubject('e13same')

    const first = await oauthLoginExpectDashboard(page, 'qq', subject)
    const username1 = await currentUsername(page)
    expect(username1).toMatch(/^qq_[0-9a-f]{8}$/)
    expect(first.join('\n')).not.toMatch(/access_token|client_secret/)

    await logoutViaUi(page)

    await oauthLoginExpectDashboard(page, 'qq', subject)
    const username2 = await currentUsername(page)
    expect(username2).toBe(username1)
  })

  test('E13-3 用户拒绝授权 → 明确提示且不产生登录态', async ({ page }) => {
    await setFakeIdentity(uniqueSubject('e13deny'))
    await startOAuthFromLogin(page, 'qq')
    await decideConsent(page, 'deny')

    await expect(page).toHaveURL(/#\/oauth\/complete/)
    await expect(page.locator('.oauth-complete .title')).toHaveText('你已取消第三方授权')
    await expect(page.locator('.oauth-complete .detail')).toHaveText('OAUTH_ACCESS_DENIED')

    await page.getByRole('button', { name: '返回登录' }).click()
    await expect(page).toHaveURL(/#\/login/)
    await expect(page.locator('.user-menu-button')).toHaveCount(0)
  })

  test('E13-4 OAuth 登录后退出登录 → 会话真实失效', async ({ page }) => {
    await oauthLoginExpectDashboard(page, 'wechat', uniqueSubject('e13logout'))
    await logoutViaUi(page)

    await page.goto('/#/dashboard')
    await expect(page).toHaveURL(/#\/login/)
  })

  test('E13-5 平台资料读取失败时仍以已核验身份完成登录', async ({ page }) => {
    const subject = uniqueSubject('e13profile')
    await setFakeIdentity(subject)
    await setFakeBehavior('profile_fail')

    await startOAuthFromLogin(page, 'wechat')
    await decideConsent(page, 'allow')
    await expect(page).toHaveURL(/#\/dashboard/)

    // 身份以已核验 subject 关联；昵称/头像缺失不得阻断登录
    const username = await currentUsername(page)
    expect(username).toMatch(/^wechat_[0-9a-f]{8}$/)
  })

  test('E13-6 登录成功后的 URL 与页面不传播第三方 code/state/token', async ({ page }) => {
    const urls = recordNavigations(page)
    await setFakeIdentity(uniqueSubject('e13leak'))
    await startOAuthFromLogin(page, 'qq')
    await decideConsent(page, 'allow')
    await expect(page).toHaveURL(/#\/dashboard/)

    // 本站前端 URL（完成页/工作台）不得携带 code / state / access_token
    const frontendUrls = urls.filter((u) => u.includes(`127.0.0.1:${process.env.JM_E2E_FRONTEND_PORT || 5373}`))
    for (const u of frontendUrls) {
      expect(u).not.toMatch(/[?&#](code|state|access_token)=/)
    }
    await expect(page.locator('body')).not.toContainText('fakeat-')
  })
})
