import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // 忽略测试产物目录：Playwright outputDir（e2e/.artifacts）在 dev root 内，
    // trace 资源快照（*.html）在测试运行中被实时写入，Vite watcher 会把它们当成
    // 新增页面向所有客户端广播 full-reload，导致被测页面中途整页刷新、OAuth
    // 完成页状态被重置（CI 上 E13-6/E14-3 的不稳定失败根因）。此目录只增不改业务
    // 代码，必须排除在热更新监听之外。
    watch: {
      ignored: [
        '**/node_modules/**',
        '**/.git/**',
        '**/e2e/.artifacts/**',
        '**/.playwright-artifacts-*/**',
      ],
    },
    proxy: {
      // 联调：业务 API 由本地后端提供（uvicorn :8000）
      // E2E 隔离环境通过 VITE_API_TARGET 覆盖目标（如 http://127.0.0.1:8123），
      // 不传时保持默认 8000，不影响日常开发。
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
