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
 * E06 发起推荐与解释展示
 * 真实链路：合成简历 → 画像确认 → baseline 推荐运行 → 评分与解释（快照）展示。
 */
test.describe('E06 发起推荐与解释展示', () => {
  test('发起匹配得到真实推荐结果并展示解释与免责声明', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)
    await uploadResumeExpectSuccess(page, `${username}_合成简历.txt`)
    await confirmProfile(page)

    await test.step('E06-1 开始匹配并得到真实推荐结果', async () => {
      await runMatching(page)
      await expect(page.locator('.job-card').first()).toBeVisible()
      await expect(page.getByText(/共为你找到 \d+ 个匹配岗位/)).toBeVisible()
    })

    await test.step('E06-2 结果卡片展示评分与解释（匹配原因）', async () => {
      const first = page.locator('.job-card').first()
      await expect(first.getByText('匹配原因')).toBeVisible()
      await expect(first.locator('.ring-text')).toContainText('匹配度')
      await expect(first.locator('.reasons .reason-item').first()).toBeVisible()
    })

    await test.step('E06-3 评分口径注明"不代表录用概率"', async () => {
      await expect(page.locator('.score-note')).toContainText('匹配分仅用于排序参考，不代表录用概率')
    })

    await test.step('E06-4 运行元信息标注画像版本与模型版本', async () => {
      await expect(page.getByText('当前使用画像版本')).toBeVisible()
      await expect(page.getByText('模型版本')).toBeVisible()
      await expect(page.locator('dd').filter({ hasText: /^v\d+$/ }).first()).toBeVisible()
    })

    await test.step('E06-5 重新进入页面可加载最近一次真实运行', async () => {
      await page.reload()
      await expect(page.locator('.job-card').first()).toBeVisible({ timeout: 15_000 })
      await expect(toast(page)).not.toContainText('匹配执行失败')
    })
  })
})
