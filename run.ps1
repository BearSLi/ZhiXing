# ============================================================
#  本地启动后端（不依赖 Docker）
#  用法： .\run.ps1
#  接口文档： http://127.0.0.1:8000/docs
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

Push-Location $backend
Write-Host "启动中…  接口文档 http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 停止`n" -ForegroundColor Gray
& $venvPy -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
Pop-Location
