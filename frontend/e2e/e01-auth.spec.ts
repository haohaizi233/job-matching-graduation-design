import { expect, test } from '@playwright/test'

import {
  BASE_URL,
  STUDENT_PASSWORD,
  loginViaUi,
  registerAccount,
  registerViaUi,
  toast,
  uniqueUsername,
} from './helpers'

/**
 * E01 注册、登录、退出
 * 真实浏览器 + 真实后端（tests/e2e/serve_backend.py），全程无 mock。
 */
test.describe('E01 注册、登录、退出', () => {
  test('UI 注册 → 登录 → 退出登录 → 再登录（真实会话撤销）', async ({ page }) => {
    const username = uniqueUsername()

    await test.step('E01-1 UI 注册成功并回到登录页', async () => {
      await registerViaUi(page, username)
      await expect(toast(page)).toContainText('注册成功，请登录')
    })

    await test.step('E01-2 登录进入工作台并展示真实用户名', async () => {
      await page.locator('#username').fill(username)
      await page.locator('#password').fill(STUDENT_PASSWORD)
      await page.getByRole('button', { name: /^登\s*录$/ }).click()
      await expect(page).toHaveURL(/#\/dashboard/)
      await expect(page.locator('.user-menu-button')).toContainText(username)
    })

    await test.step('E01-3 退出登录真正清除会话并回到登录页', async () => {
      await page.getByRole('button', { name: '个人账户菜单' }).click()
      await page.getByRole('button', { name: '退出登录' }).click()
      await expect(page).toHaveURL(/#\/login/)
      await expect(page.locator('#username')).toBeVisible()
    })

    await test.step('E01-4 同一账号可再次登录（服务端会话非一次性）', async () => {
      await loginViaUi(page, username)
      await expect(page.locator('.user-menu-button')).toContainText(username)
    })
  })

  test('E01 登录凭证错误给出真实错误提示且不进入工作台', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)

    await page.goto('/#/login')
    await page.locator('#username').fill(username)
    await page.locator('#password').fill('WrongPass!2026x')
    await page.getByRole('button', { name: /^登\s*录$/ }).click()

    await expect(page).toHaveURL(/#\/login/)
    await expect(page.locator('form [role="alert"]')).not.toBeEmpty()
  })
})
