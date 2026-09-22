# 部署说明（Deployment Guide）

> 适用：把工单系统交付到任何一台机器上运行
> 两条路线：**A. Docker（推荐）** ／ **B. 本地虚拟环境（无需 Docker）**

---

## 0. 交付物清单

```
ticket-system/
├── backend/                 后端（FastAPI + SQLite）
│   ├── main.py              应用装配入口
│   ├── deps.py              认证与授权依赖
│   ├── requirements.txt     钉死版本的依赖清单
│   ├── Dockerfile           镜像构建说明
│   ├── .dockerignore        不进镜像的文件
│   ├── entrypoint.sh        容器启动入口（数据库自检）
│   ├── bootstrap_db.py      幂等数据库初始化
│   ├── .env.example         环境变量模板
│   ├── prompts/             Prompt 模板（资产）
│   └── tests/               pytest 测试套件
├── frontend/index.html      前端页面
├── setup.ps1                一键初始化（路线 B）
├── run.ps1                  一键启动（路线 B）
├── deploy-docker.ps1        一键构建并运行容器（路线 A）
└── deploy-docker.sh         WSL/Linux 版（路线 A 备选）
```

---

## 1. 环境要求

| 项目 | 路线 A（Docker） | 路线 B（本地） |
|---|---|---|
| 操作系统 | Windows 10/11 + WSL2，或任意 Linux | 任意 |
| 运行时 | Docker Engine 20+ | Python 3.11+ |
| 磁盘 | 镜像约 300 MB + 数据卷 | 约 200 MB（含虚拟环境） |
| 网络 | 首次构建需能访问 PyPI | 首次安装需能访问 PyPI |

---

## 2. 路线 A：Docker 部署（推荐）

### 2.1 准备配置

```powershell
cd ticket-system\backend
Copy-Item .env.example .env
# 编辑 .env，至少填两项：
#   SECRET_KEY   —— 随机密钥，生成命令：
#                   python -c "import secrets; print(secrets.token_hex(32))"
#   LLM_API_KEY  —— 大模型 API Key（不填则 AI 功能不可用，其余功能正常）
```

> ⚠️ `.env` 已被 `.gitignore` 和 `.dockerignore` 双重排除。
> **它不会进 git，也不会进镜像**——密钥只在运行时注入。

### 2.2 一键构建 + 运行

```powershell
cd ticket-system
.\deploy-docker.ps1
```

脚本做的事（等价手动命令）：

```powershell
docker build -t ticket-system:v1 backend

docker run -d --name ticket-api -p 8000:8000 `
  --env-file backend\.env `
  -e DB_PATH=/app/data/app.db `
  -v "<项目路径>\data:/app/data" `
  ticket-system:v1
```

### 2.3 三个关键参数，为什么必须这样写

| 参数 | 作用 | 不写会怎样 |
|---|---|---|
| `--env-file .env` | **运行时**注入密钥 | 密钥被打进镜像 → 镜像一分发即泄露；改密钥还要重新构建 |
| `-e DB_PATH=/app/data/app.db` | 容器内数据库路径 | 走默认 `/app/app.db` → 写到容器临时层，容器一删数据全没 |
| `-v <宿主目录>:/app/data` | 数据卷 | 同上，数据无法持久化 |

> 为什么 `DB_PATH` 不写进 `.env`？
> 因为 `.env` 是**本地开发和容器共用**的。写死 `/app/data/app.db` 后，本地直接跑 `uvicorn` 会因为 Windows 上没有该路径而失败。
> **原则：环境相关的配置按"谁在哪个环境用"分层注入。**

### 2.4 验证

```powershell
docker ps                                  # 状态应为 Up (healthy)
docker logs -f ticket-api                  # 看到 "Uvicorn running on http://0.0.0.0:8000"
curl.exe http://127.0.0.1:8000/            # 返回 JSON
```

浏览器打开 <http://127.0.0.1:8000/docs> → 应看到 6 个接口。

### 2.5 常用运维命令

```powershell
docker logs -f ticket-api          # 实时日志
docker stop ticket-api             # 停止
docker start ticket-api            # 启动
docker rm -f ticket-api            # 删除容器（数据仍在 data/ 目录）
docker rmi ticket-system:v1        # 删除镜像
docker exec -it ticket-api sh      # 进入容器排查
```

### 2.6 数据备份与恢复

数据库就是一个文件：`<项目路径>\data\app.db`

```powershell
# 备份
Copy-Item data\app.db "data\app.db.bak-$(Get-Date -Format yyyyMMdd)"
# 恢复：停容器 → 覆盖文件 → 起容器
docker stop ticket-api
Copy-Item data\app.db.bak-20260922 data\app.db -Force
docker start ticket-api
```

---

## 3. 路线 B：本地虚拟环境（无 Docker）

### 3.1 一键初始化

```powershell
cd ticket-system
.\setup.ps1
```

它做四件事：建 `.venv` → 按 `requirements.txt` 装依赖 → 生成 `.env` 并写入随机 `SECRET_KEY` → 初始化数据库（建表 + 种子数据 + 设置演示密码）。

### 3.2 启动

```powershell
.\run.ps1
# 或手动：
#   cd backend
#   ..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

### 3.3 回归验证

```powershell
# 零依赖版（不需要额外安装任何东西）
cd backend
python verify_all.py

# pytest 版（需先安装 pytest 与 httpx）
python -m pip install pytest httpx
python -m pytest
```

### 3.4 接口冒烟测试

```powershell
cd backend
.\test.ps1          # 铁三角检查 + 三人权限对照 + AI 四项验收
```

---

## 4. 演示账号

| 用户名 | 密码 | 角色 | 部门 | 可见范围 |
|---|---|---|---|---|
| zhangsan | 123456 | employee | 技术部 | 仅自己的工单 |
| lisi | 123456 | manager | 技术部 | 本部门全部工单 |
| wangwu | 123456 | finance | 财务部 | 仅自己的工单 |

> 密码策略当前为"仅自己的"，是**业务决策**而非技术限制。
> 若要放开财务看全量，在 `services/ticket_service.py` 的 `apply_scope` 中**显式新增一行**
> `if role == "finance": return where, params` —— 让这次授权在代码里可见、可 review、可追溯。

---

## 5. 常见问题排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 容器起来了但宿主机访问不到 | 应用监听了 `127.0.0.1` | 必须 `--host 0.0.0.0` |
| `docker logs` 报数据库无此表 | 数据卷为空且 entrypoint 未执行初始化 | 确认 `entrypoint.sh` 有执行权限；手动 `docker exec ticket-api python bootstrap_db.py` |
| 本地跑 `uvicorn` 报路径错误 | `.env` 里混入了容器路径 | `.env` 里**不要**写 `DB_PATH`，容器路径用 `-e` 传 |
| 登录报 `无效的登录凭证` | `SECRET_KEY` 变了（重建了 .env） | 旧 token 失效属正常，重新登录即可 |
| AI 接口 500，日志显示未配置 Key | 缺少 `LLM_API_KEY` | 在 `.env` 里填 Key 后**重启服务**（`load_dotenv` 只在启动时读一次） |
| `docker build` 报路径含中文错误 | 构建上下文路径含非 ASCII | 把项目复制到纯英文路径（如 `~/ticket-system`）后构建 |
| 每次构建都要重装依赖，很慢 | `COPY . .` 放在了 `pip install` 之前 | 保持 Dockerfile 顺序：先 `COPY requirements.txt` |

---

## 6. 生产环境还需补充什么（诚实的差距清单）

当前实现面向内部工具 / 演示环境，距离严格生产标准还有以下差距：

1. **数据库**：SQLite 单文件，不支持并发写扩展 → 换 PostgreSQL
2. **应用服务器**：单进程 uvicorn → 前面加 Nginx，用 gunicorn 多 worker
3. **密钥管理**：`.env` 文件 → 换成 KMS / Vault / 云厂商密钥服务
4. **CI/CD**：手工构建 → 流水线（测试 → 构建 → 推送镜像 → 部署）
5. **可观测性**：只打日志 → 加指标（Prometheus）+ 链路追踪 + 告警
6. **备份**：手工拷贝 → 定时备份 + 恢复演练
7. **HTTPS**：当前 HTTP → 证书 + 反向代理
8. **容器加固**：以 root 运行 → 非 root 用户 + 只读根文件系统

> 面试时主动说出这份差距清单，比声称"我的系统已经生产就绪"可信得多。
