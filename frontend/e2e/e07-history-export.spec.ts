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
 * E07 推荐历史与 CSV 导出
 * 历史来自真实 recommendation 运行记录；导出为前端 CSV 生成（浏览器真实下载事件）。
 */
test.describe('E07 推荐历史与 CSV 导出', () => {
  test('推荐历史展示真实运行记录并可导出 CSV', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)
    await uploadResumeExpectSuccess(page, `${username}_合成简历.txt`)
    await confirmProfile(page)
    await runMatching(page)

    await test.step('E07-1 推荐历史展示本次真实运行', async () => {
      await page.getByRole('button', { name: '推荐历史', exact: true }).click()
      await expect(page.getByRole('heading', { name: '历史记录' })).toBeVisible()
      await expect(page.getByText('该状态下暂无历史记录。')).toHaveCount(0)
      await expect(page.getByRole('heading', { name: /推荐结果 ·/ })).toBeVisible()
    })

    await test.step('E07-2 导出 CSV（真实浏览器下载）', async () => {
      const [download] = await Promise.all([
        page.waitForEvent('download'),
        page.getByRole('button', { name: '导出结果' }).click(),
      ])
      expect(download.suggestedFilename()).toMatch(/^推荐历史_\d{4}-\d{2}-\d{2}\.csv$/)
      const stream = await download.createReadStream()
      const chunks: Buffer[] = []
      for await (const chunk of stream) chunks.push(chunk as Buffer)
      const csv = Buffer.concat(chunks).toString('utf-8')
      expect(csv).toContain('匹配时间')
      expect(csv).toContain('画像版本')
      await expect(toast(page)).toContainText(/已导出 \d+ 条记录/)
    })
  })
})
