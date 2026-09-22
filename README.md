# 工单系统 · 内部工具 + AI 助手

一个面向企业内部场景的**全栈 AI 应用**示例：工单提交 → 主管审批 → 状态流转 → 按权限查看 → AI 起草审批意见 / AI 问答查询。

项目重点不在功能数量，而在**把一条完整链路做扎实**：认证与授权、行级数据权限、事务与状态机、AI 集成与 AI 安全、日志与部署。

---

## 目录

- [功能一览](#功能一览)
- [技术栈](#技术栈)
- [架构](#架构)
- [快速开始](#快速开始)
- [演示账号](#演示账号)
- [项目结构](#项目结构)
- [设计要点](#设计要点)
- [测试](#测试)
- [文档索引](#文档索引)
- [已知限制与下一步](#已知限制与下一步)

---

## 功能一览

| 模块 | 能力 |
|---|---|
| 认证 | 登录换取 JWT；密码 bcrypt 哈希存储；认证失败信息不可区分（防用户名枚举） |
| 授权 | 角色门禁（功能权限）+ 行级数据范围（数据权限），**默认拒绝** |
| 工单 | 创建 / 列表（分页、状态筛选）/ 审批，带状态机校验与流转日志 |
| AI 起草 | 主管请求 AI 为待审批工单生成审批意见（提示词模板化） |
| AI 问答 | Function Calling 让 AI 查询工单数据，**查询范围恒等于提问者自身权限** |
| 前端 | 登录 → 自动带 token 请求 → 列表渲染，含 XSS 转义与 401 统一处理 |
| 交付 | Docker 镜像 + 一键脚本 + 幂等数据库初始化 + 部署文档 |

---

## 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 前端 | 原生 HTML / CSS / JavaScript | 刻意不用框架，先看清"发请求 → 收数据 → 渲染"三件事的原始形态 |
| 后端 | FastAPI | 自动生成 OpenAPI 文档；依赖注入便于统一鉴权与资源管理 |
| 数据 | SQLite（`sqlite3` 标准库） | 零外部依赖；换 PostgreSQL 只需改连接层 |
| 鉴权 | PyJWT + bcrypt | 无状态 token；密码哈希自带随机盐 |
| AI | OpenAI 兼容 SDK | 换供应商只改 `.env` 三行，业务代码零改动 |
| 部署 | Docker | 多阶段层缓存、密钥运行时注入、数据卷持久化 |

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│ 前端  frontend/index.html                                │
│   localStorage 存 token → fetch + Authorization 头        │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / JSON（CORS 白名单）
                           ▼
┌─────────────────────────────────────────────────────────┐
│ FastAPI  main.py（装配层）                                │
│  routers/auth.py   routers/tickets.py   routers/ai.py    │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│ deps.py  认证与授权                                       │
│   get_current_user  验签 → 查库 → 得到当前用户            │
│   require_role(...) 角色门禁 → 403                        │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│ services/  业务层（不感知 HTTP）                          │
│   ticket_service  apply_scope 行级权限入口                │
│   ai_service      权限校验 → 模板渲染 → 调模型 / 工具循环  │
│   llm_service     LLM 适配层（供应商可替换）               │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│ database.py  yield 依赖：连接创建 → 交出 → 自动释放        │
│ SQLite   users / tickets / ticket_logs                   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼  HTTPS（后端在此变成客户端）
                    外部大模型服务
```

---

## 快速开始

### 方式一：Docker（推荐）

```powershell
cd ticket-system\backend
Copy-Item .env.example .env      # 填入 SECRET_KEY 与 LLM_API_KEY

cd ..
.\deploy-docker.ps1              # 构建镜像 + 启动容器
```

→ 打开 <http://127.0.0.1:8000/docs>

（Linux / WSL 用户：`bash deploy-docker.sh`）

### 方式二：本地虚拟环境

```powershell
cd ticket-system
.\setup.ps1                      # 建虚拟环境 + 装依赖 + 生成 .env + 初始化数据库
.\run.ps1                        # 启动
```

### 填配置

`.env` 需要两项：

```ini
SECRET_KEY=<python -c "import secrets; print(secrets.token_hex(32))">
LLM_API_KEY=sk-xxx               # 不填则 AI 功能不可用，其余功能正常
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

---

## 演示账号

| 用户名 | 密码 | 角色 | 部门 | 可见工单范围 |
|---|---|---|---|---|
| `zhangsan` | `123456` | employee | 技术部 | 仅自己提交的 |
| `lisi` | `123456` | manager | 技术部 | 本部门全部 |
| `wangwu` | `123456` | finance | 财务部 | 仅自己提交的 |

> 用不同账号登录同一页面，看到的工单列表不同——这是数据权限的直观演示。

---

## 项目结构

```
ticket-system/
├── backend/
│   ├── main.py              应用装配（挂载路由、中间件）
│   ├── config.py            配置读取（.env → 常量）
│   ├── database.py          连接管理（yield 依赖）
│   ├── deps.py              认证与授权依赖
│   ├── schemas.py           Pydantic 模型（请求/响应契约）
│   ├── routers/             HTTP 层：auth / tickets / ai
│   ├── services/            业务层：auth / ticket / ai / llm
│   ├── prompts/             Prompt 模板（资产）
│   ├── tests/               pytest 测试套件
│   ├── bootstrap_db.py      幂等数据库初始化
│   ├── verify_all.py        零依赖回归验证
│   ├── init_db.py           建表脚本（教学用）
│   ├── seed_data.py         种子数据（教学用）
│   ├── reset_passwords.py   重置演示密码（教学用）
│   ├── test.ps1             接口冒烟测试
│   ├── Dockerfile           镜像构建
│   ├── entrypoint.sh        容器启动入口
│   ├── requirements.txt     依赖（版本钉死）
│   └── .env.example         环境变量模板
├── frontend/index.html      前端页面
├── docs/                    文档
│   ├── deploy.md            部署说明
│   ├── api.md               接口文档
│   ├── dev-standards.md     开发规范
│   └── prompts.md           Prompt 模板说明
├── setup.ps1 / run.ps1      本地一键脚本
├── deploy-docker.ps1 / .sh  Docker 一键脚本
└── README.md
```

---

## 设计要点

### 1. 权限：默认拒绝 + 双层检查

```python
def apply_scope(where, params, viewer):
    role = viewer["role"]
    if role == "admin":   return where, params                                   # 显式授权
    if role == "manager": return where + " AND u.department = ?", ...
    if role in ("employee", "finance"):
                          return where + " AND t.user_id = ?", ...
    return where + " AND 1 = 0", params                                          # 未知角色 → 空
```

- **功能权限**（`require_role`）：你能不能按这个按钮 → 403
- **数据权限**（`apply_scope`）：列表里有没有这一行 → 空/403
- **未列举的角色一律看不到数据**：新增角色时不会静默获得权限

### 2. 身份只来自 token

请求体不接受 `user_id`。用别人的 token 无法以你的名义建单，用你的 token 也无法冒充别人（防 IDOR）。

### 3. AI 安全：权限检查先于模型调用

大模型是外部服务，发送数据即数据出境。因此顺序固定为：
**校验存在性 → 校验部门 → 校验状态 → 才拼提示词 → 才调用模型**。

### 4. AI 没有特权通道

Function Calling 的工具执行复用 `list_tickets`，强制经过 `apply_scope`：

> 让 AI"列出全公司工单"只会得到你自己那些——防线不在提示词里，在 SQL 的 `WHERE` 里。

工具四层防御：参数 `enum` 白名单 / 只暴露只读工具 / 执行强制过权限 / 数据与指令结构分离。

### 5. 资源生命周期收敛到一处

数据库连接由 `get_db()` 的 yield 依赖统一创建与释放，业务层与路由层均不手动 `close()`。

### 6. 可替换的模型适配层

`llm_service` 是唯一与模型供应商打交道的地方。换模型只改 `.env` 三行：

```ini
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4-flash
```

---

## 测试

```powershell
cd backend

python verify_all.py            # 零依赖回归验证（20 项，无需安装任何东西）

python -m pip install pytest httpx
python -m pytest                # pytest 套件（需 httpx）

.\test.ps1                      # 接口冒烟：服务存活 + 多身份对照 + AI 验收
```

**回归测试锁定了以下历史缺陷**（每个修过的 bug 都变成了一条测试）：

| 测试 | 锁定的缺陷 |
|---|---|
| `test_unknown_role_sees_nothing` | 权限兜底放行（任何新角色自动获得全量数据权限） |
| `test_create_ignores_body_user_id` | 提交人取自请求体（水平越权） |
| `test_approve_cross_department_forbidden` | 只做功能权限、漏做数据权限 |
| `test_ask_with_tool_call_and_complete_history` | Function Calling 工具调用历史缺环 |
| `test_draft_reply_permission_checked_before_llm_call` | 权限校验晚于模型调用（数据提前出境） |

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/api.md](docs/api.md) | 接口约定、鉴权方式、错误码、权限矩阵 |
| [docs/deploy.md](docs/deploy.md) | 两条部署路线、参数取舍、备份恢复、故障排查 |
| [docs/dev-standards.md](docs/dev-standards.md) | 分层/接口/安全/AI 协作/测试/Git 规范 |
| [docs/prompts.md](docs/prompts.md) | 提示词资产化、编写规范、安全边界 |
| `/docs`（运行后） | FastAPI 自动生成的在线可交互 API 文档 |

---

## 已知限制与下一步

| 限制 | 影响 | 下一步 |
|---|---|---|
| SQLite 单文件 | 不支持高并发写 | 换 PostgreSQL |
| 单进程 uvicorn | 无法水平扩展 | Nginx + gunicorn 多 worker |
| 密钥存 `.env` | 不适合多环境管控 | 接入 KMS / Vault |
| 无 CI/CD | 构建部署靠手工脚本 | 加流水线：测试 → 构建 → 推镜像 → 部署 |
| 前端为原生实现 | 复杂交互会吃力 | 迁移 React + 组件库 |
| 无刷新 token 机制 | token 过期需重新登录 | 引入 refresh token |
| 日志仅输出到标准输出 | 无检索与告警 | 接入集中式日志与指标 |
