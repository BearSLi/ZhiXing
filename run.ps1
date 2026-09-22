# ============================================================
#  本地启动后端（不依赖 Docker）
#  用法： .\run.ps1
#  接口文档： http://127.0.0.1:8000/docs
#
#  启动前会做一次依赖自检：虚拟环境若是按旧的 requirements.txt 建的，
#  这里会自动把缺的包装上，避免启动时报出难以理解的错误。
# ============================================================
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Host "未找到虚拟环境，请先执行 .\setup.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Host "缺少 backend\.env，请先执行 .\setup.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "=== 依赖自检 ===" -ForegroundColor Cyan
Push-Location $backend
& $venvPy check_deps.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "检测到依赖缺失，正在自动安装…" -ForegroundColor Yellow
    & $venvPy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "依赖安装失败，请检查网络后重试" -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Write-Host "依赖已补齐" -ForegroundColor Green
}
Pop-Location

Push-Location $backend
Write-Host "`n启动中…  接口文档 http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 停止`n" -ForegroundColor Gray
& $venvPy -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
Pop-Location
