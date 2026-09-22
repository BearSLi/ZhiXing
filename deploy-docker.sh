#!/usr/bin/env bash
# ============================================================
#  在 WSL / Linux 里构建并运行容器（PowerShell 脚本的等价版本）
#  适用场景：Windows 上装不了 Docker Desktop，改在 WSL 里装 Docker Engine
#  用法： bash deploy-docker.sh
# ============================================================
set -e

IMAGE_NAME="${IMAGE_NAME:-ticket-system:v1}"
CONTAINER_NAME="${CONTAINER_NAME:-ticket-api}"
PORT="${PORT:-8000}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
DATA_DIR="$ROOT/data"
ENV_FILE="$BACKEND/.env"

echo "=== [1/5] 前置检查 ==="
if ! command -v docker >/dev/null 2>&1; then
    echo "未找到 docker 命令。请在 WSL 里安装：sudo apt install -y docker.io" >&2
    exit 1
fi
docker --version
[ -f "$ENV_FILE" ] || { echo "缺少 backend/.env，请先复制 .env.example 并填写" >&2; exit 1; }
mkdir -p "$DATA_DIR"

echo
echo "=== [2/5] 构建镜像 $IMAGE_NAME ==="
docker build -t "$IMAGE_NAME" "$BACKEND"

echo
echo "=== [3/5] 清理同名旧容器 ==="
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

echo
echo "=== [4/5] 启动容器 ==="
docker run -d --name "$CONTAINER_NAME" -p "${PORT}:8000" \
    --env-file "$ENV_FILE" \
    -e DB_PATH=/app/data/app.db \
    -v "$DATA_DIR:/app/data" \
    "$IMAGE_NAME"

echo
echo "=== [5/5] 检查状态 ==="
sleep 4
docker ps --filter "name=$CONTAINER_NAME" --format "  容器: {{.Names}}  状态: {{.Status}}  端口: {{.Ports}}"

echo
echo "✅ 部署完成"
echo "   接口文档: http://127.0.0.1:$PORT/docs"
echo "   查看日志: docker logs -f $CONTAINER_NAME"
echo "   停止:     docker stop $CONTAINER_NAME"
echo "   删除:     docker rm -f $CONTAINER_NAME   (数据仍在 $DATA_DIR)"
