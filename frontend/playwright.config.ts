import { defineConfig, devices } from '@playwright/test'

/**
 * Phase5-3 / M3 浏览器 E2E 配置（真实前后端，隔离测试环境）。
 *
 * 隔离纪律：
 *  - 后端由 tests/e2e/serve_backend.py 启动：独立 sqlite（tests/e2e/.runtime/e2e.db）
 *    + 独立私有存储（tests/e2e/.runtime/storage），绝不触碰 data/private/dev.db 与生产库；
 *  - 种子数据全部为合成夹具（tests/e2e/fixtures.py，is_synthetic=True）；
 *  - 测试账号在用例内注册，用户名带随机后缀，互不干扰。
 */
const BACKEND_PORT = Number(process.env.JM_E2E_PORT || 8123)
// E2E 前端专用端口（默认 5373，避开日常开发 5173 被其它项目占用导致误连）：
// 上一轮失败根因就是 5173 被另一项目的 Vite 静默复用（reuseExistingServer），
// 浏览器连到错误应用全用例超时。现改为专用端口 + 不复用外来服务。
const FRONTEND_PORT = Number(process.env.JM_E2E_FRONTEND_PORT || 5373)
// Phase8-A：E2E 用模拟第三方授权服务器（浏览器可访问的假微信/QQ/微博授权页）
const FAKE_OAUTH_PORT = Number(process.env.JM_E2E_FAKE_OAUTH_PORT || 8125)
// Python 启动命令：Windows 本地默认 py -3.13；CI（Linux）用 JM_E2E_PYTHON=python 覆盖
const PY = process.env.JM_E2E_PYTHON || 'py -3.13'

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/.artifacts',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: [
    ['list'],
    ['json', { outputFile: './e2e/.artifacts/e2e-raw.json' }],
  ],
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'zh-CN',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // Phase8-A：模拟第三方授权服务器（仅 E2E；浏览器真实跳转授权页并点击同意/拒绝）
      command: `${PY} tests/e2e/fake_oauth_server.py`,
      cwd: '..',
      url: `http://127.0.0.1:${FAKE_OAUTH_PORT}/health`,
      reuseExistingServer: true,
      timeout: 60_000,
      env: {
        PYTHONUTF8: '1',
        JM_E2E_FAKE_OAUTH_PORT: String(FAKE_OAUTH_PORT),
        JM_E2E_FAKE_REDIRECT_ALLOW: `http://127.0.0.1:${BACKEND_PORT}/api/v1/auth/oauth/`,
      },
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: `${PY} tests/e2e/serve_backend.py`,
      cwd: '..',
      url: `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`,
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        PYTHONUTF8: '1',
        PYTHONPATH: 'src',
        JM_E2E_PORT: String(BACKEND_PORT),
        JM_E2E_FRONTEND_ORIGIN: `http://127.0.0.1:${FRONTEND_PORT}`,
        JM_E2E_FAKE_OAUTH_URL: `http://127.0.0.1:${FAKE_OAUTH_PORT}`,
      },
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      // Windows 上 vite 默认只监听 ::1，显式绑定 127.0.0.1 与探活 URL 一致；端口占用直接失败
      //（不 reuse：外来同端口服务必须显式失败，禁止静默连到错误应用）
      command: `npm run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT} --strictPort`,
      cwd: '.',
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        VITE_API_TARGET: `http://127.0.0.1:${BACKEND_PORT}`,
      },
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
})
