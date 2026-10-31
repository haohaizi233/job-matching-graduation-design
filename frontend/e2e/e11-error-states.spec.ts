import { expect, test } from '@playwright/test'

import { BASE_URL, loginViaUi, registerAccount, uniqueUsername } from './helpers'

/**
 * E11 空数据、网络错误与 API 失败
 *
 * 真实行为（api/dashboard.ts `settle`）：单项数据源失败**不静默吞掉**，
 * 也不伪造统计，而是在「数据来源提示」登记 `XX暂不可用（错误码）` 并降级为空态。
 */
test.describe('E11 空数据、网络错误与 API 失败', () => {
  test('空数据展示合理空态与引导', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)

    await expect(
      page.getByText('暂无推荐结果。先上传简历并确认画像，再从「智能匹配」发起推荐。'),
    ).toBeVisible()
  })

  test('网络中断登记真实错误码并降级为空态（无假数据）', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)

    await page.route('**/api/v1/**', (route) => route.abort('failed'))
    await page.reload()

    const notes = page.locator('.data-notes')
    await expect(notes).toBeVisible()
    await expect(notes).toContainText('暂不可用（NETWORK_ERROR）')
    // 降级后不得伪造统计或推荐卡片
    await expect(notes).toContainText('简历列表暂不可用')
    await expect(
      page.getByText('暂无推荐结果。先上传简历并确认画像，再从「智能匹配」发起推荐。'),
    ).toBeVisible()

    await test.step('E11-恢复：网络恢复后数据来源提示消失', async () => {
      await page.unroute('**/api/v1/**')
      await page.reload()
      await expect(notes).toHaveCount(0)
      await expect(
        page.getByText('暂无推荐结果。先上传简历并确认画像，再从「智能匹配」发起推荐。'),
      ).toBeVisible()
    })
  })

  test('服务端 500 展示真实错误码且不展示假数据', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)

    await page.route('**/api/v1/**', (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: { code: 'INTERNAL_ERROR', message: '内部错误（E2E 注入）' } }),
      }),
    )
    await page.reload()

    const notes = page.locator('.data-notes')
    await expect(notes).toBeVisible()
    await expect(notes).toContainText('暂不可用（INTERNAL_ERROR）')
    // 失败降级后仍展示空态引导，而不是伪造的统计/推荐
    await expect(
      page.getByText('暂无推荐结果。先上传简历并确认画像，再从「智能匹配」发起推荐。'),
    ).toBeVisible()
  })
})
