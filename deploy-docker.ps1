# ============================================================
#  构建并运行 Docker 容器
#  用法： .\deploy-docker.ps1
#         .\deploy-docker.ps1 -Port 9000 -ImageName ticket-system:v2
# ============================================================
param(
    [string]$ImageName = "ticket-system:v1",
    [string]$ContainerName = "ticket-api",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$dataDir = Join-Path $root "data"
$envFile = Join-Path $backend ".env"

Write-Host "=== [1/5] 前置检查 ===" -ForegroundColor Cyan
docker --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "未找到 docker 命令。请先安装 Docker Desktop，或在 WSL 里使用 docker。" -ForegroundColor Red
    Write-Host "（若 WSL 里装了 docker，可在 WSL 终端执行： bash deploy-docker.sh）" -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $envFile)) {
    Write-Host "缺少 backend\.env，请先执行 .\setup.ps1" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
    Write-Host "  已创建数据目录 $dataDir"
}

Write-Host "`n=== [2/5] 构建镜像 $ImageName ===" -ForegroundColor Cyan
docker build -t $ImageName $backend
if ($LASTEXITCODE -ne 0) { Write-Host "构建失败" -ForegroundColor Red; exit 1 }

Write-Host "`n=== [3/5] 清理同名旧容器 ===" -ForegroundColor Cyan
docker rm -f $ContainerName 2>$null | Out-Null

Write-Host "`n=== [4/5] 启动容器 ===" -ForegroundColor Cyan
# 三个关键点：
#   --env-file      运行时注入密钥（镜像里没有密钥）
#   -e DB_PATH      容器专属的数据库路径（不写进 .env，避免影响本地开发）
#   -v              数据卷：数据库文件落在宿主机，容器删除也不丢数据
docker run -d --name $ContainerName -p "${Port}:8000" `
    --env-file $envFile `
    -e DB_PATH=/app/data/app.db `
    -v "${dataDir}:/app/data" `
    $ImageName
if ($LASTEXITCODE -ne 0) { Write-Host "启动失败" -ForegroundColor Red; exit 1 }

Write-Host "`n=== [5/5] 检查状态 ===" -ForegroundColor Cyan
Start-Sleep -Seconds 4
docker ps --filter "name=$ContainerName" --format "  容器: {{.Names}}  状态: {{.Status}}  端口: {{.Ports}}"

Write-Host "`n✅ 部署完成" -ForegroundColor Green
Write-Host "   接口文档: http://127.0.0.1:$Port/docs" -ForegroundColor Gray
Write-Host "   查看日志: docker logs -f $ContainerName" -ForegroundColor Gray
Write-Host "   停止:     docker stop $ContainerName" -ForegroundColor Gray
Write-Host "   删除:     docker rm -f $ContainerName   (数据仍在 $dataDir)" -ForegroundColor Gray
