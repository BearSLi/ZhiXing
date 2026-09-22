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
| 认证 | 登录换取 JWT；密码 bcrypt 哈希存储；认证失败信息不可区分（防用户名枚举）；密钥缺失则拒绝启动 |
| 授权 | 角色门禁（功能权限）+ 行级数据范围（数据权限），**默认拒绝**；admin 豁免部门限制 |
| 工单 | 创建 / 详情 / 列表（分页、状态筛选）/ 流转日志 / 流转动作（**通过 · 驳回 · 关闭**），带状态机校验与并发保护 |
| AI 起草 | 主管请求 AI 为待审批工单生成审批意见（提示词模板化 + 数据/指令分隔防注入） |
| AI 问答 | Function Calling 让 AI 查询工单数据，**查询范围恒等于提问者自身权限** |
| 前端 | 登录 → 自动带 token 请求 → 列表渲染，含 XSS 转义与 401 统一处理 |
| 错误契约 | 所有响应（成功与失败）统一为 `{code, message, data}` 信封；全局异常处理器 |
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

演示数据刻意设计成**能体现出权限差异**——否则"主管看得更多"这件事根本看不出来。

| 用户名 | 密码 | 角色 | 部门 | 可见工单 | 说明 |
|---|---|---|---|---|---|
| `zhangsan` | `123456` | employee | 技术部 | 3 条 | 只看自己的 |
| `zhaoliu` | `123456` | employee | 技术部 | 2 条 | 与 zhangsan **同部门但看不到对方的单子** |
| `lisi` | `123456` | manager | 技术部 | 6 条 | 看到技术部全员（= 上面两人的并集 + 自己的） |
| `wangwu` | `123456` | finance | 财务部 | 1 条 | 只看自己的；技术部主管也看不到他的 |
| `admin1` | `123456` | admin | 管理部 | 7 条 | 看全部，且可跨部门处理 |

**演示要点**：`zhangsan`(3) 与 `zhaoliu`(2) 同为技术部员工，可见集合**互不相交**；
`lisi`(6) 恰好等于技术部三人可见范围的**并集**；跨部门的 `wangwu` 的单子不在 `lisi` 视野里。
一个数字矩阵就能说清"行级数据权限"这件事。

**重新生成干净的演示数据**（会删除现有数据库并重建）：

```powershell
cd backend
..\.venv\Scripts\python.exe bootstrap_db.py --reset
```

脚本结束时会打印上面那张可见条数矩阵，方便对照验证。

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
连接建立时统一加固：`foreign_keys=ON`（SQLite 默认不强制外键约束）、`journal_mode=WAL`、`busy_timeout=5000`。

### 6. 状态机 + 并发保护

```python
ALLOWED_TRANSITIONS = {
    "pending":  {"approve", "reject"},
    "approved": {"close"},
    "rejected": set(),      # 终态
    "closed":   set(),      # 终态
}
```

流转不用"先 SELECT 判断、再 UPDATE"——那样两个并发请求可能都读到 `pending`、
都通过检查、都写日志（TOCTOU 竞态）。而是把状态写进 WHERE 条件：

```python
cur = conn.execute("UPDATE tickets SET status=? WHERE id=? AND status=?", ...)
if cur.rowcount != 1:
    raise ConflictError("工单状态已被他人变更，请刷新后重试")   # 409
```

由数据库保证"只有一个人能改成功"。`verify_all.py` 里有一个**真实的两线程并发用例**验证这一点。

### 7. 统一错误契约

成功与失败都走同一种信封，前端只需实现一次错误处理：

```json
{ "code": 403, "message": "只能处理本部门的工单", "detail": "只能处理本部门的工单", "data": null }
```

`detail` 字段保留是为了向后兼容既有前端与脚本（契约演进策略：新字段先加，旧字段留一版再删）。

### 8. 可替换的模型适配层

`llm_service` 是唯一与模型供应商打交道的地方。换模型只改 `.env` 三行：

```ini
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4-flash
```

---

## 测试

```powershell
cd backend

python verify_all.py            # 零依赖回归验证（29 项，service 层，无需安装任何东西）

python -m pip install pytest httpx
python -m pytest                # pytest 套件（HTTP 层，需 httpx）

python http_check.py            # HTTP 契约验收（16 项，需服务已启动）
#   python -m uvicorn main:app --port 8001
#   python http_check.py http://127.0.0.1:8001

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
| `test_rejected_is_terminal` | 状态机只有半张表（reject/close 无法到达） |
| `test_cannot_act_on_own_ticket` | 主管可以审批自己提交的工单 |
| `test_admin_exempt_from_department_check` | 管理员被数据权限挡在门外（功能权限与数据权限不自洽） |
| 并发审批用例（verify_all [7]） | 先查后改导致的 TOCTOU 竞态（重复审批 + 日志翻倍） |
| HTTP 校验用例（http_check） | 自定义校验器异常导致 422 被兜底成 500 |

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
