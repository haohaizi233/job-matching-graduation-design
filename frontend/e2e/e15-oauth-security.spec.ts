import { expect, request as playwrightRequest, test } from '@playwright/test'

import {
  BASE_URL,
  loginViaUi,
  registerAccount,
  toast,
  uniqueUsername,
} from './helpers'
import {
  BACKEND_URL,
  decideConsent,
  findNavigation,
  logoutViaUi,
  recordNavigations,
  resetFakeProvider,
  setFakeBehavior,
  setFakeIdentity,
  startOAuthFromLogin,
  uniqueSubject,
} from './oauth-helpers'

/**
 * E15 OAuth 安全基线（真实前后端）：
 * 未配置平台不产生假成功 / 伪造与重放的 state 被拒 / 一次性票据不可重放 /
 * 开放重定向被拒 / 平台异常不伪装成密码错误。
 */
test.describe('E15 OAuth 安全基线', () => {
  test.beforeEach(async () => {
    await resetFakeProvider()
  })

  test('E15-1 未配置凭据的平台显示暂未开放且不产生假成功', async ({ page }) => {
    await test.step('E15-1a 登录页微博按钮禁用并标注暂未开放', async () => {
      await page.goto('/#/login')
      const weibo = page.getByRole('button', { name: '微博登录' })
      await expect(weibo).toBeDisabled()
      await expect(weibo).toContainText('暂未开放')
    })

    await test.step('E15-1b /providers 返回未配置原因（不含任何 Secret）', async () => {
      const ctx = await playwrightRequest.newContext({ baseURL: BACKEND_URL })
      try {
        const res = await ctx.get('/api/v1/auth/oauth/providers')
        expect(res.status()).toBe(200)
        const raw = await res.text()
        expect(raw).not.toMatch(/client_secret|e2e-fake-secret/)
        const body = JSON.parse(raw) as {
          data: { providers: { id: string; enabled: boolean; reason_code?: string | null }[] }
        }
        const weibo = body.data.providers.find((p) => p.id === 'weibo')
        expect(weibo?.enabled).toBe(false)
        expect(weibo?.reason_code).toBe('OAUTH_PROVIDER_NOT_CONFIGURED')
      } finally {
        await ctx.dispose()
      }
    })

    await test.step('E15-1c 未配置平台发起授权返回明确错误（无假授权链接）', async () => {
      const ctx = await playwrightRequest.newContext({ baseURL: BACKEND_URL })
      try {
        const res = await ctx.post('/api/v1/auth/oauth/start', {
          data: { provider: 'weibo', mode: 'login', return_path: '/dashboard' },
        })
        expect(res.status()).toBe(503)
        const body = (await res.json()) as { error?: { code?: string } }
        expect(body.error?.code).toBe('OAUTH_PROVIDER_NOT_CONFIGURED')
      } finally {
        await ctx.dispose()
      }
    })

    await test.step('E15-1d 设置页未开放平台不可发起绑定', async () => {
      const username = uniqueUsername('e15off')
      await registerAccount(BASE_URL, username)
      await loginViaUi(page, username)
      await page.goto('/#/settings')
      const weiboRow = page
        .locator('section.panel')
        .filter({ hasText: '第三方账号绑定' })
        .locator('.device-row')
        .filter({ hasText: '微博' })
      await expect(weiboRow).toContainText('该平台暂未开放（凭据尚未配置）')
      await expect(weiboRow.getByRole('button', { name: '绑定' })).toBeDisabled()
    })
  })

  test('E15-2 伪造 state 的回调被拒绝（CSRF 防线）', async ({ page }) => {
    await page.goto(
      `${BACKEND_URL}/api/v1/auth/oauth/wechat/callback?code=forged-code&state=forged-state`,
    )
    await expect(page).toHaveURL(/#\/oauth\/complete/)
    await expect(page.locator('.oauth-complete .title')).toHaveText('第三方登录未完成，请重试')
    await expect(page.locator('.oauth-complete .detail')).toHaveText('OAUTH_INVALID_STATE')

    await page.getByRole('button', { name: '返回登录' }).click()
    await expect(page).toHaveURL(/#\/login/)
    await expect(page.locator('.user-menu-button')).toHaveCount(0)
  })

  test('E15-3 回调重放（state/code 二次消费）被拒绝', async ({ page }) => {
    const urls = recordNavigations(page)
    await setFakeIdentity(uniqueSubject('e15replay'))
    await startOAuthFromLogin(page, 'wechat')
    await decideConsent(page, 'allow')
    await expect(page).toHaveURL(/#\/dashboard/)

    const callbackUrl = findNavigation(urls, /\/api\/v1\/auth\/oauth\/wechat\/callback\?/)
    expect(callbackUrl).not.toBe('')
    expect(callbackUrl).toMatch(/code=/)
    await logoutViaUi(page)

    // 同一 callback（含同一 state/code）重放 -> 明确拒绝且不再产生会话
    await page.goto(callbackUrl)
    await expect(page).toHaveURL(/#\/oauth\/complete/)
    await expect(page.locator('.oauth-complete .detail')).toHaveText('OAUTH_CALLBACK_REPLAY')
    await page.goto('/#/dashboard')
    await expect(page).toHaveURL(/#\/login/)
  })

  test('E15-4 一次性登录票据重放被拒绝', async ({ page }) => {
    const urls = recordNavigations(page)
    await setFakeIdentity(uniqueSubject('e15ticket'))
    await startOAuthFromLogin(page, 'qq')
    await decideConsent(page, 'allow')
    await expect(page).toHaveURL(/#\/dashboard/)

    const completeUrl = findNavigation(urls, /#\/oauth\/complete\?/)
    expect(completeUrl).not.toBe('')
    await logoutViaUi(page)

    // 重放完成页（票据已被消费 / 浏览器绑定凭据已清除）-> 不再签发新会话
    await page.goto(completeUrl)
    await expect(page).toHaveURL(/#\/oauth\/complete/)
    await expect(page.locator('.oauth-complete .title')).toContainText(
      /登录凭证已(过期|被使用)/,
    )
    await page.goto('/#/dashboard')
    await expect(page).toHaveURL(/#\/login/)
  })

  test('E15-5 return_path 开放重定向被拒绝', async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BACKEND_URL })
    try {
      const badPaths = [
        'https://evil.example/steal',
        '//evil.example/steal',
        '/\\evil.example/steal',
        '/%2F%2Fevil.example/steal',
        '/dashboard/../../evil',
      ]
      for (const returnPath of badPaths) {
        const res = await ctx.post('/api/v1/auth/oauth/start', {
          data: { provider: 'wechat', mode: 'login', return_path: returnPath },
        })
        expect(res.status(), `return_path=${returnPath}`).toBe(400)
        const body = (await res.json()) as { error?: { code?: string } }
        expect(body.error?.code).toBe('OAUTH_INVALID_REDIRECT')
      }

      // 站内白名单路径正常放行（正向对照）
      const ok = await ctx.post('/api/v1/auth/oauth/start', {
        data: { provider: 'wechat', mode: 'login', return_path: '/settings' },
      })
      expect(ok.status()).toBe(200)
      const data = (await ok.json()) as { data?: { return_path?: string } }
      expect(data.data?.return_path).toBe('/settings')
    } finally {
      await ctx.dispose()
    }
  })

  test('E15-6 第三方平台异常不伪装成密码错误', async ({ page }) => {
    await setFakeIdentity(uniqueSubject('e15err'))
    await setFakeBehavior('http_500')

    await startOAuthFromLogin(page, 'wechat')
    await decideConsent(page, 'allow')
    await expect(page).toHaveURL(/#\/oauth\/complete/)
    await expect(page.locator('.oauth-complete .title')).toHaveText('第三方登录未完成，请重试')
    await expect(page.locator('.oauth-complete .detail')).toHaveText('OAUTH_PROVIDER_UNAVAILABLE')

    // 错误提示不得出现「密码错误」类文案，也不得泄露平台令牌
    const text = (await page.locator('body').innerText()).replace(/\s+/g, '')
    expect(text).not.toContain('密码错误')
    expect(text).not.toContain('fakeat-')
    await expect(toast(page)).not.toContainText('密码')
  })

  test('E15-7 code 换 token 失败（code 过期）给出明确错误', async ({ page }) => {
    await setFakeIdentity(uniqueSubject('e15expired'))
    await setFakeBehavior('code_expired')

    await startOAuthFromLogin(page, 'qq')
    await decideConsent(page, 'allow')
    await expect(page).toHaveURL(/#\/oauth\/complete/)
    await expect(page.locator('.oauth-complete .detail')).toHaveText('OAUTH_TOKEN_EXCHANGE_FAILED')
    await expect(page.locator('.oauth-complete .title')).toHaveText('第三方登录未完成，请重试')
  })
})
