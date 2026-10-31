import { expect, request as playwrightRequest, type Page } from '@playwright/test'

/**
 * Phase5-3 / M3 E2E 共享助手。
 *
 * 纪律（对齐 tests/e2e/fixtures.py）：
 *  - 测试账号/简历/岗位全部为合成夹具（用户名随机后缀、简历文本标注"合成"）；
 *  - 只打真实后端（tests/e2e/serve_backend.py 起的隔离实例），禁止 mock 业务响应；
 *  - 断言以"状态等待"为准（expect 自动重试），不使用固定 sleep。
 */

/** E2E 前端基址（playwright.config.ts 的 baseURL；可用 JM_E2E_BASE_URL 覆盖） */
export const BASE_URL = process.env.JM_E2E_BASE_URL || 'http://127.0.0.1:5173'

/** 合成学生密码（与 tests/e2e/fixtures.py 的 STUDENT_PASSWORD 一致） */
export const STUDENT_PASSWORD = 'E2eStudent!2026'

/** 合成简历正文（与 tests/e2e/fixtures.py 的 SYNTHETIC_RESUME_TEXT 一致） */
export const SYNTHETIC_RESUME_TEXT = `王五（E2E 合成简历，非真人，仅供自动化端到端测试）
求职意向：Java 开发工程师
最高学历：本科
专业：软件工程
毕业年份：2027
期望城市：上海、杭州
工作性质：全职

专业技能
- 熟练掌握 Java、Spring Boot、MySQL
- 熟悉 Python、Docker、Linux

教育背景
2023-2027 合成大学 软件工程专业 本科

项目经历
- 开发招聘管理演示系统，使用 Java 与 Spring Boot，负责简历解析模块

实习经历
- 合成科技公司 后端开发实习生，负责接口开发与联调

证书
- CET-6
`

/** 无法抽出任何结构化字段的合成乱码正文（用于"部分解析"路径） */
export const SYNTHETIC_BAD_RESUME_TEXT = `E2E-SYNTHETIC unparseable payload @#$%^&* ~!@#$%^&*()_+
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
`

export function uniqueUsername(prefix = 'e2e_s'): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`
}

/** 通过真实后端 API 注册（业务流程之外的账号准备；被测流程仍在 UI 中执行） */
export async function registerAccount(
  baseURL: string,
  username: string,
  password = STUDENT_PASSWORD,
): Promise<void> {
  const ctx = await playwrightRequest.newContext({ baseURL })
  try {
    const res = await ctx.post('/api/v1/auth/register', {
      data: { username, password, email: `${username}@synthetic.test` },
    })
    const body = await res.json().catch(() => null)
    if (!res.ok()) {
      const code = (body as { error?: { code?: string } } | null)?.error?.code ?? res.status()
      throw new Error(`E2E 账号注册失败（${code}）：${JSON.stringify(body)}`)
    }
  } finally {
    await ctx.dispose()
  }
}

/** UI 登录（E01/E09 覆盖登录本身；其余用例复用以获得真实会话） */
export async function loginViaUi(
  page: Page,
  username: string,
  password = STUDENT_PASSWORD,
): Promise<void> {
  await page.goto('/#/login')
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: /^登\s*录$/ }).click()
  await expect(page).toHaveURL(/#\/dashboard/)
}

/** UI 注册（E01 专用） */
export async function registerViaUi(
  page: Page,
  username: string,
  password = STUDENT_PASSWORD,
): Promise<void> {
  await page.goto('/#/login')
  await page.getByRole('tab', { name: '注册' }).click()
  await page.locator('#username').fill(username)
  await page.locator('#email').fill(`${username}@synthetic.test`)
  await page.locator('#password').fill(password)
  await page.locator('#confirmPassword').fill(password)
  await page.getByRole('button', { name: /^注\s*册$/ }).click()
}

/** 全局 Toast（ToastHost 固定挂载，role=status） */
export function toast(page: Page) {
  return page.locator('.toast-host')
}

/** 侧边导航跳转 */
export async function gotoNav(page: Page, label: string): Promise<void> {
  await page.getByRole('button', { name: label, exact: true }).click()
}

/** 上传合成简历（真实走 FileReader → /resumes/json → 解析落库） */
export async function uploadResumeFile(
  page: Page,
  fileName: string,
  content: string,
): Promise<void> {
  await page.locator('input[type="file"]').setInputFiles({
    name: fileName,
    mimeType: 'text/plain',
    buffer: Buffer.from(content, 'utf-8'),
  })
}

/** 上传合成简历并等待上传成功提示 */
export async function uploadResumeExpectSuccess(
  page: Page,
  fileName: string,
  content = SYNTHETIC_RESUME_TEXT,
): Promise<void> {
  await gotoNav(page, '简历管理')
  await expect(page.getByRole('heading', { name: '上传新简历' })).toBeVisible()
  await uploadResumeFile(page, fileName, content)
  await expect(toast(page)).toContainText('上传成功')
}

/** 等画像真实加载完成（画像未加载时编辑/确认动作会落空，不能误判为成功） */
export async function waitForProfileLoaded(page: Page): Promise<void> {
  await expect(page.getByText('当前画像版本')).toBeVisible()
  await expect(
    page.locator('.edit-field', { hasText: '专业' }).locator('input'),
  ).not.toHaveValue('', { timeout: 15_000 })
}

/** 我的画像 → 确认当前画像（推荐前置） */
export async function confirmProfile(page: Page): Promise<void> {
  await gotoNav(page, '我的画像')
  await waitForProfileLoaded(page)
  await page.getByRole('button', { name: '确认当前画像' }).click()
  await expect(toast(page)).toContainText('画像已确认')
}

/** 智能匹配 → 开始匹配并等待结果 */
export async function runMatching(page: Page): Promise<void> {
  await gotoNav(page, '智能匹配')
  await expect(page.getByRole('button', { name: '开始匹配' })).toBeVisible()
  await page.getByRole('button', { name: '开始匹配' }).click()
  await expect(toast(page)).toContainText(/匹配完成，共为你找到 \d+ 个岗位/)
}
