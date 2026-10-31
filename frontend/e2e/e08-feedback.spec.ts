import { expect, test } from '@playwright/test'

import {
  BASE_URL,
  confirmProfile,
  loginViaUi,
  registerAccount,
  runMatching,
  toast,
  uniqueUsername,
  uploadResumeExpectSuccess,
} from './helpers'

/**
 * E08 反馈提交与状态回显
 * 反馈提交真实写入后端（/recommendations/{runId}/feedback），刷新后从服务端回显。
 */
test.describe('E08 反馈提交与状态回显', () => {
  test('提交反馈 → 提示成功 → 刷新后状态从服务端回显', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)
    await uploadResumeExpectSuccess(page, `${username}_合成简历.txt`)
    await confirmProfile(page)
    await runMatching(page)

    await test.step('E08-1 反馈中心展示来自推荐明细的待反馈记录', async () => {
      await page.getByRole('button', { name: '反馈中心', exact: true }).click()
      await expect(page.getByRole('heading', { name: '反馈记录' })).toBeVisible()
      await expect(page.locator('.record-table .status-badge.pending').first()).toBeVisible()
    })

    await test.step('E08-2 提交「感兴趣」反馈', async () => {
      await page.locator('.record-table .table-row').first().click()
      await expect(page.getByRole('heading', { name: '反馈详情' })).toBeVisible()
      await page.locator('.detail-panel').getByRole('button', { name: '感兴趣', exact: true }).click()
      await expect(toast(page)).toContainText(/已将「.+」标记为感兴趣/)
    })

    await test.step('E08-3 刷新后状态从服务端回显（非前端内存态）', async () => {
      await page.reload()
      await expect(page.getByRole('heading', { name: '反馈记录' })).toBeVisible()
      await expect(page.locator('.record-table .status-badge.interested').first()).toBeVisible()
    })

    await test.step('E08-4 反馈统计随真实记录更新', async () => {
      await expect(page.getByText('反馈总数')).toBeVisible()
      await expect(page.locator('.detail-panel').getByRole('button', { name: '感兴趣', exact: true })).toBeVisible()
    })
  })
})
