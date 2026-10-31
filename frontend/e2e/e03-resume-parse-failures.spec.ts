import { expect, test } from '@playwright/test'

import {
  BASE_URL,
  SYNTHETIC_BAD_RESUME_TEXT,
  loginViaUi,
  registerAccount,
  toast,
  uniqueUsername,
  uploadResumeFile,
} from './helpers'

/**
 * E03 简历解析失败及重试
 * 失败路径全部来自真实后端错误（EMPTY_INPUT / PARSE_FAILED / 部分解析），
 * 重试走真实 reparse 接口；不使用任何假成功响应。
 */
test.describe('E03 简历解析失败及重试', () => {
  test('空文件 / 损坏文档报错，不可解析正文标记部分解析，并可重新解析', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)
    await page.getByRole('button', { name: '简历管理', exact: true }).click()
    await expect(page.getByRole('heading', { name: '上传新简历' })).toBeVisible()

    await test.step('E03-1 空文件 → EMPTY_INPUT 错误提示且不入库', async () => {
      await uploadResumeFile(page, `${username}_空简历.txt`, '')
      await expect(toast(page)).toContainText('正文为空')
      await expect(page.getByText('共 0 份简历')).toBeVisible()
    })

    await test.step('E03-2 损坏 docx（非 zip 结构）→ PARSE_FAILED 错误提示且不入库', async () => {
      await page.locator('input[type="file"]').setInputFiles({
        name: `${username}_损坏简历.docx`,
        mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        buffer: Buffer.from('this is not a real docx / not a zip archive', 'utf-8'),
      })
      await expect(toast(page)).toContainText(/DOCX 文件损坏|文档解析失败/)
      await expect(page.getByText('共 0 份简历')).toBeVisible()
    })

    await test.step('E03-3 乱码正文入库并如实标记「部分解析」', async () => {
      const badName = `${username}_乱码简历.txt`
      await uploadResumeFile(page, badName, SYNTHETIC_BAD_RESUME_TEXT)
      await expect(page.getByText(badName)).toBeVisible()
      const row = page.locator('.resume-table tbody tr').filter({ hasText: badName })
      await expect(row.locator('.status-cell')).toContainText('部分解析')
    })

    await test.step('E03-4 行内「重新解析」走真实 reparse 并刷新状态', async () => {
      const row = page
        .locator('.resume-table tbody tr')
        .filter({ hasText: `${username}_乱码简历.txt` })
      await row.locator('.menu-btn').click()
      await page.getByRole('button', { name: '重新解析', exact: true }).click()
      await expect(toast(page)).toContainText('重新解析完成')
      await expect(row.locator('.status-cell')).toContainText('部分解析')
    })
  })
})
