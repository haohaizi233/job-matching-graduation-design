import { expect, test } from '@playwright/test'

import {
  BASE_URL,
  loginViaUi,
  registerAccount,
  uniqueUsername,
} from './helpers'

/**
 * E09 未认证及 Token 失效
 * 权限隔离以服务端 401 为准；前端守卫与会话复位只是体验层。
 */
test.describe('E09 未认证及 Token 失效', () => {
  test('未登录访问受保护页被引导到登录页', async ({ page }) => {
    await page.goto('/#/dashboard')
    await expect(page).toHaveURL(/#\/login/)
    await expect(page.locator('#username')).toBeVisible()

    await page.goto('/#/matching')
    await expect(page).toHaveURL(/#\/login/)
  })

  test('未带 Token 的业务 API 由服务端拒绝（401）', async ({ page }) => {
    const res = await page.request.get('/api/v1/auth/me')
    expect(res.status()).toBe(401)
    const body = await res.json()
    expect(body?.error?.code || '').toBeTruthy()
  })

  test('失效 Token 触发全局会话复位并回到登录页', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)
    await expect(page.locator('.user-menu-button')).toContainText(username)

    await page.evaluate(() => localStorage.setItem('jm_token', 'invalid-e2e-token'))
    await page.reload()

    await expect(page).toHaveURL(/#\/login/, { timeout: 15_000 })
    await expect(page.locator('#username')).toBeVisible()
    // 不得在失效后继续展示用户信息
    await expect(page.locator('.user-menu-button')).toHaveCount(0)
    // 本地会话已清除
    const token = await page.evaluate(() => localStorage.getItem('jm_token'))
    expect(token).toBeFalsy()
  })
})
