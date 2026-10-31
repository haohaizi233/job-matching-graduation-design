import { expect, test } from '@playwright/test'

import {
  BASE_URL,
  confirmProfile,
  loginViaUi,
  registerAccount,
  runMatching,
  uniqueUsername,
  uploadResumeExpectSuccess,
} from './helpers'

/**
 * E10 多用户数据隔离
 * 用户 A 产生简历/推荐/反馈数据后，用户 B 登录必须看不到任何 A 的数据。
 */
test.describe('E10 多用户数据隔离', () => {
  test('用户 B 看不到用户 A 的简历、推荐历史与反馈', async ({ page }) => {
    const userA = uniqueUsername('e2e_a')
    const userB = uniqueUsername('e2e_b')
    const fileA = `${userA}_合成简历.txt`

    await test.step('E10-1 用户 A 上传简历并完成一次推荐', async () => {
      await registerAccount(BASE_URL, userA)
      await loginViaUi(page, userA)
      await uploadResumeExpectSuccess(page, fileA)
      await confirmProfile(page)
      await runMatching(page)
      await page.getByRole('button', { name: '推荐历史', exact: true }).click()
      await expect(page.getByRole('heading', { name: /推荐结果 ·/ })).toBeVisible()
    })

    await test.step('E10-2 退出 A 并登录 B', async () => {
      await page.getByRole('button', { name: '个人账户菜单' }).click()
      await page.getByRole('button', { name: '退出登录' }).click()
      await expect(page).toHaveURL(/#\/login/)
      await registerAccount(BASE_URL, userB)
      await loginViaUi(page, userB)
    })

    await test.step('E10-3 B 的简历列表为空且不含 A 的文件', async () => {
      await page.getByRole('button', { name: '简历管理', exact: true }).click()
      await expect(page.getByText('共 0 份简历')).toBeVisible()
      await expect(page.getByText(fileA)).toHaveCount(0)
    })

    await test.step('E10-4 B 的推荐历史为空', async () => {
      await page.getByRole('button', { name: '推荐历史', exact: true }).click()
      await expect(page.getByText('该状态下暂无历史记录。')).toBeVisible()
    })

    await test.step('E10-5 B 的反馈中心为空', async () => {
      await page.getByRole('button', { name: '反馈中心', exact: true }).click()
      await expect(page.getByText('没有符合条件的反馈记录。')).toBeVisible()
    })
  })
})
