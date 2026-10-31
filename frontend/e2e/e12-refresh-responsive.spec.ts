import { expect, test } from '@playwright/test'

import { BASE_URL, loginViaUi, registerAccount, uniqueUsername } from './helpers'

/**
 * E12 主要页面刷新与基础响应式检查
 * 刷新后会话与业务数据保持；缩窄视口后核心导航与内容仍可用。
 */
test.describe('E12 页面刷新与基础响应式检查', () => {
  test('刷新后会话保持，缩小视口核心功能仍可用', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)

    await test.step('E12-1 刷新后仍保持登录与工作台数据', async () => {
      await expect(page.locator('.user-menu-button')).toContainText(username)
      await page.reload()
      await expect(page).toHaveURL(/#\/dashboard/)
      await expect(page.locator('.user-menu-button')).toContainText(username)
    })

    await test.step('E12-2 1024×768 视口下导航与内容可用', async () => {
      await page.setViewportSize({ width: 1024, height: 768 })
      await expect(page.getByRole('button', { name: '简历管理', exact: true })).toBeVisible()
      await page.getByRole('button', { name: '简历管理', exact: true }).click()
      await expect(page.getByRole('heading', { name: '上传新简历' })).toBeVisible()
    })

    await test.step('E12-3 恢复 1280×800 后页面正常', async () => {
      await page.setViewportSize({ width: 1280, height: 800 })
      await expect(page.getByRole('heading', { name: '上传新简历' })).toBeVisible()
      await page.getByRole('button', { name: '工作台', exact: true }).click()
      await expect(page).toHaveURL(/#\/dashboard/)
    })

    await test.step('E12-4 记录视口横向溢出情况（度量项）', async () => {
      const overflow = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
      }))
      expect(overflow.innerWidth).toBe(1280)
      // 度量值写入测试输出，供报告引用；不作为通过门槛
      console.log(`E12 viewport overflow metric: scrollWidth=${overflow.scrollWidth} innerWidth=${overflow.innerWidth}`)
    })
  })
})
