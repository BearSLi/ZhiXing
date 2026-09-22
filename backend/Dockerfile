# ============================================================
#  工单系统后端 · Docker 镜像构建文件
#  构建：docker build -t ticket-system:v1 .
#  运行：docker run -d --name ticket-api -p 8000:8000 \
#          --env-file .env -e DB_PATH=/app/data/app.db \
#          -v "<宿主机data目录>:/app/data" ticket-system:v1
# ============================================================

# ① 基础镜像：slim 版体积小、攻击面小；版本钉死保证可复现
#    不用 latest —— 今天的 latest 和明天的可能是两个不同的东西
FROM python:3.12-slim

# ② 工作目录：容器内的"项目根"
WORKDIR /app

# ③ 让 Python 日志不缓冲（否则 docker logs 看不到实时输出）
ENV PYTHONUNBUFFERED=1

# ④ 先只拷依赖清单 —— 这一行的位置是 Dockerfile 最重要的技巧：
#    改动最少的放前面，改动最频繁的（代码）放后面
#    → 改代码时依赖层命中缓存，构建从几分钟降到几秒
COPY requirements.txt .

# ⑤ 装依赖（--no-cache-dir 不保留 pip 缓存，镜像更小）
RUN pip install --no-cache-dir -r requirements.txt

# ⑥ 再拷代码（.dockerignore 会自动排除 .env / app.db / __pycache__ 等）
COPY . .

# ⑦ 数据目录 + 入口脚本可执行权限
#    /app/data 是卷的挂载点，先建好避免挂载时权限问题
RUN mkdir -p /app/data && chmod +x entrypoint.sh

# ⑧ 声明容器对外提供 8000 端口（文档作用，真正的映射靠 docker run -p）
EXPOSE 8000

# ⑨ 健康检查：Docker 定期探活，容器状态会显示 healthy/unhealthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/')" || exit 1

# ⑩ 启动入口：先确保数据库就绪（不存在则初始化），再交棒给下面的 CMD
ENTRYPOINT ["./entrypoint.sh"]

# ⑪ 启动命令：
#    - 必须监听 0.0.0.0（监听 127.0.0.1 的话宿主机连不进来，这是新手最经典的坑）
#    - 不用 --reload（那是开发用的，生产不需要文件监控）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── 进一步加固（可选，工作流稳定后再做）──
# 创建非 root 用户运行，降低容器逃逸风险：
#   RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
#   USER appuser
# 注意：需要同步保证挂载的数据卷对该用户可写
