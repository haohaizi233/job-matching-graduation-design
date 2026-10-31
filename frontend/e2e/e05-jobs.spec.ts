import { expect, test } from '@playwright/test'

import {
  BASE_URL,
  loginViaUi,
  registerAccount,
  toast,
  uniqueUsername,
} from './helpers'

/**
 * E05 岗位查询、筛选与详情
 * 岗位来自后端 jobs 接口（E2E 种子岗位全部 is_synthetic=True）。
 */
test.describe('E05 岗位查询、筛选与详情', () => {
  test('岗位列表真实加载 → 关键词筛选 → 详情页 → 返回列表', async ({ page }) => {
    const username = uniqueUsername()
    await registerAccount(BASE_URL, username)
    await loginViaUi(page, username)

    await test.step('E05-1 岗位探索展示后端真实岗位', async () => {
      await page.getByRole('button', { name: '岗位探索', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Java 开发工程师（E2E 合成岗位）' })).toBeVisible()
      await expect(page.getByRole('heading', { name: '前端开发工程师（E2E 合成岗位）' })).toBeVisible()
    })

    await test.step('E05-2 关键词搜索过滤列表', async () => {
      await page.locator('input[placeholder*="搜索岗位名称"]').fill('Java')
      await page.getByRole('button', { name: '搜索岗位' }).click()
      await expect(toast(page)).toContainText('搜索「Java」')
      await expect(page.getByRole('heading', { name: 'Java 开发工程师（E2E 合成岗位）' })).toBeVisible()
      await expect(page.getByRole('heading', { name: '前端开发工程师（E2E 合成岗位）' })).toHaveCount(0)
    })

    await test.step('E05-3 详情页展示真实 JD 内容', async () => {
      await page.getByRole('button', { name: '查看详情' }).first().click()
      await expect(page).toHaveURL(/#\/job\//)
      await expect(page.getByRole('heading', { name: 'Java 开发工程师（E2E 合成岗位）' })).toBeVisible()
      await expect(page.getByRole('heading', { name: '岗位职责' })).toBeVisible()
      await expect(page.getByRole('heading', { name: '任职要求' })).toBeVisible()
    })

    await test.step('E05-4 面包屑返回岗位列表', async () => {
      await page.getByRole('button', { name: '岗位探索' }).first().click()
      await expect(page).toHaveURL(/#\/jobs/)
    })
  })
})
