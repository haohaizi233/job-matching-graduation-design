# Phase5-3 / M3 浏览器 E2E 一键运行（干净环境）
#
# 纪律：
#  1. 每次全量运行前重建隔离运行目录 tests/e2e/.runtime（独立 sqlite + 独立存储）；
#  2. 重启 E2E 后端进程——注册限流为进程内内存桶（20/小时/客户端），
#     复用旧进程会因多次迭代运行触发 RATE_LIMITED，重启保证 20 的预算只属于本次运行；
#  3. 运行真实 Playwright（Chromium）+ 真实前后端，随后生成验收报告（只做格式转换）。
#
# 用法（任意目录）：
#   powershell -ExecutionPolicy Bypass -File tests\e2e\run_e2e.ps1
#   powershell -ExecutionPolicy Bypass -File tests\e2e\run_e2e.ps1 -Filter e06   # 只跑部分用例
param(
    [string]$Filter = "",
    [string]$RunId = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # 仓库根目录
if (-not $RunId) { $RunId = "m3-e2e-" + (Get-Date -Format "yyyyMMdd-HHmmss") }

Write-Host "== [1/4] 停止旧的 E2E 服务（8123 后端 / 5173 前端）"
foreach ($port in 8123, 5173) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "   killed port $port (pid $($conn.OwningProcess))"
    }
}
Start-Sleep -Seconds 2

Write-Host "== [2/4] 清空隔离运行目录 tests/e2e/.runtime"
Remove-Item -Recurse -Force (Join-Path $root "tests\e2e\.runtime") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $root "frontend\e2e\.artifacts") -ErrorAction SilentlyContinue

Write-Host "== [3/4] 运行 Playwright E2E（RunId=$RunId）"
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "src"
$env:JM_RUN_ID = $RunId
Set-Location (Join-Path $root "frontend")
$argsList = @("playwright", "test")   # reporter 由 playwright.config.ts 提供（list + json）
if ($Filter) { $argsList += $Filter }
& npx @argsList
$pwExit = $LASTEXITCODE
Write-Host "   playwright exit=$pwExit"

Write-Host "== [4/4] 生成 E2E 验收报告"
Set-Location $root
& py -3.13 tests/e2e/build_report.py
$reportExit = $LASTEXITCODE
Write-Host "   report exit=$reportExit"

if ($pwExit -ne 0) { exit $pwExit }
exit $reportExit
