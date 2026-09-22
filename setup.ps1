# ============================================================
#  环境初始化（不依赖 Docker）
#  做四件事：建虚拟环境 → 装依赖 → 生成 .env → 初始化数据库
#  用法：在 ticket-system 目录下执行  .\setup.ps1
# ============================================================
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "=== [1/4] 检查 Python ===" -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "未找到 Python，请先安装 Python 3.11 以上版本" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== [2/4] 创建虚拟环境并安装依赖 ===" -ForegroundColor Cyan
if (-not (Test-Path $venvPy)) {
    python -m venv (Join-Path $root ".venv")
    Write-Host "  已创建 .venv"
} else {
    Write-Host "  .venv 已存在，跳过创建"
}
& $venvPy -m pip install --upgrade pip -q
& $venvPy -m pip install -r (Join-Path $backend "requirements.txt")
Write-Host "  依赖安装完成"

Write-Host "`n=== [3/4] 准备 .env ===" -ForegroundColor Cyan
$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $backend ".env.example") $envFile
    # 自动生成一个随机 SECRET_KEY，省得用户手填
    $key = & $venvPy -c "import secrets; print(secrets.token_hex(32))"
    (Get-Content $envFile -Raw) -replace 'SECRET_KEY=.*', "SECRET_KEY=$key" |
        Set-Content $envFile -Encoding UTF8 -NoNewline
    Write-Host "  已从 .env.example 生成 .env，并自动写入随机 SECRET_KEY" -ForegroundColor Green
    Write-Host "  ⚠️  还需手动填入 LLM_API_KEY（AI 功能才可用）" -ForegroundColor Yellow
} else {
    Write-Host "  .env 已存在，跳过"
}

Write-Host "`n=== [4/4] 初始化数据库 ===" -ForegroundColor Cyan
Push-Location $backend
& $venvPy bootstrap_db.py
Pop-Location

Write-Host "`n✅ 初始化完成" -ForegroundColor Green
Write-Host "   下一步： .\run.ps1      启动后端（本地直跑）" -ForegroundColor Gray
Write-Host "   或：     .\test.ps1     跑一遍接口回归（需服务已启动）" -ForegroundColor Gray
