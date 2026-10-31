import { expect, test } from '@playwright/test'

import {
  BASE_URL,
  loginViaUi,
  registerAccount,
  toast,
  uniqueUsername,
  uploadResumeExpectSuccess,
} from './helpers'

/**
 * E04 画像修改、确认、版本历史
 * 人工修订保存为新画像版本（带 expectedVersion 乐观锁），确认后才用于智能匹配。
 */
test.describe('E04 画像修改、确认、版本历史', () => {
  test('修改画像字段 → 保存新版本 → 确认 → 版本历史可回看', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)
    await uploadResumeExpectSuccess(page, `${username}_合成简历.txt`)

    await page.getByRole('button', { name: '我的画像', exact: true }).click()
    await expect(page.getByText('当前画像版本')).toBeVisible()

    await test.step('E04-1 人工修订毕业年份并保存为新版本', async () => {
      const field = page.locator('.edit-field', { hasText: '毕业年份' }).locator('input')
      await field.fill('2029')
      await page.getByRole('button', { name: '保存修改' }).click()
      await expect(toast(page)).toContainText('画像修改已保存为新版本')
    })

    await test.step('E04-2 确认当前画像（推荐前置条件）', async () => {
      await page.getByRole('button', { name: '确认当前画像' }).click()
      await expect(toast(page)).toContainText('画像已确认，可用于智能匹配')
    })

    await test.step('E04-3 版本历史展开多个真实版本', async () => {
      await page.getByRole('button', { name: '版本历史' }).click()
      const items = page.locator('.version-list .version-item')
      await expect(items.first()).toBeVisible()
      expect(await items.count()).toBeGreaterThanOrEqual(2)
    })

    await test.step('E04-4 回看历史版本（只读预览）', async () => {
      await page.locator('.version-list .version-item button').first().click()
      await expect(toast(page)).toContainText(/正在预览 v\d+|已返回当前版本/)
    })
  })
})
