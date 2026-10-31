import { expect, test } from '@playwright/test'

import {
  BASE_URL,
  loginViaUi,
  registerAccount,
  uniqueUsername,
  uploadResumeExpectSuccess,
} from './helpers'

/**
 * E02 上传简历与解析
 * 链路：上传合成简历 → 文本抽取 → 结构化解析落库 → 画像可核对。
 */
test.describe('E02 上传简历与解析', () => {
  test('上传合成简历 → 简历列表显示解析结果 → 我的画像呈现抽取字段', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)

    const fileName = `${username}_合成简历.txt`

    await test.step('E02-1 上传合成简历并提示成功', async () => {
      await uploadResumeExpectSuccess(page, fileName)
    })

    await test.step('E02-2 简历列表出现该文件且解析状态为真实解析结果', async () => {
      await expect(page.getByText(fileName)).toBeVisible()
      const row = page.locator('.resume-table tbody tr').filter({ hasText: fileName })
      await expect(row).toHaveCount(1)
      await expect(row.locator('.status-cell')).toContainText('解析完成')
      await expect(row.locator('.version')).toContainText('v1')
    })

    await test.step('E02-3 我的画像展示真实抽取字段（非静态占位）', async () => {
      await page.getByRole('button', { name: '我的画像', exact: true }).click()
      await expect(page.getByText('当前画像版本')).toBeVisible()
      // 人工修订区回填的是本次解析结果
      await expect(page.locator('.edit-field', { hasText: '专业' }).locator('input')).toHaveValue(
        /软件工程/,
      )
      await expect(
        page.locator('.edit-field', { hasText: '求职意向' }).locator('input'),
      ).toHaveValue(/Java/)
    })

    await test.step('E02-4 列表统计与文件元数据来自真实记录', async () => {
      await page.getByRole('button', { name: '简历管理', exact: true }).click()
      await expect(page.getByText(fileName)).toBeVisible()
      await expect(page.getByText('共 1 份简历')).toBeVisible()
    })
  })
})
