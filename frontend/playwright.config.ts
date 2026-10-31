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
const FRONTEND_PORT = 5173

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
      command: 'py -3.13 tests/e2e/serve_backend.py',
      cwd: '..',
      url: `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`,
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        PYTHONUTF8: '1',
        PYTHONPATH: 'src',
        JM_E2E_PORT: String(BACKEND_PORT),
      },
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      // Windows 上 vite 默认只监听 ::1，显式绑定 127.0.0.1 与探活 URL 一致；端口占用直接失败
      command: 'npm run dev -- --host 127.0.0.1 --strictPort',
      cwd: '.',
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        VITE_API_TARGET: `http://127.0.0.1:${BACKEND_PORT}`,
      },
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
})
