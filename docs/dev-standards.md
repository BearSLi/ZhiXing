# 开发规范（Development Standards）

> 目的：让代码在这个项目里**长得一样**，让安全与可维护性**不依赖个人记忆**。
> 每条规范后面尽量附上"为什么"——规则如果不能解释原因，就会被绕过。

---

## 一、分层规范

```
请求 →  routers/     路由层：只负责"收参数、调服务、包响应"
          ↓
        services/    业务层：真正的大脑，不碰 HTTP
          ↓
        database.py  数据访问：只负责连接与生命周期
```

| 层 | 该做 | **不该做** |
|---|---|---|
| `routers/` | 声明路径与依赖、参数校验（Pydantic）、把 `BizError` 翻译成 HTTP 状态码 | ❌ 写 SQL ❌ 写业务规则 ❌ 开关数据库连接 |
| `services/` | 业务规则、权限过滤、事务边界、抛 `BizError` | ❌ `import fastapi` ❌ 抛 `HTTPException` ❌ 感知当前是 HTTP 还是定时任务 |
| `database.py` | 连接的创建与释放（yield 依赖） | ❌ 业务逻辑 |

### 1.1 为什么业务层不能抛 `HTTPException`

`HTTPException` 是 FastAPI 的类，它的含义是"把异常翻译成 HTTP 响应"。一旦业务层抛它，就等于宣称"我此刻一定活在一次 HTTP 请求里"。

```python
# ❌ 业务层耦合了 Web 框架
def close_overdue(conn):
    raise HTTPException(400, "无超时工单")   # 定时任务调用它时：这是个它不认识的异常

# ✅ 业务层只描述"发生了什么"
def close_overdue(conn):
    raise BizError("无超时工单", code=400)    # 路由层翻译成 400；定时任务翻译成一条日志
```

**原则：业务层说"发生了什么"，调用方决定"怎么表达"。**

### 1.2 资源所有权

> **谁创建，谁关闭；使用方绝不越权释放。**

数据库连接由 `get_db()` 的 yield 依赖创建，就由它关闭：

```python
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn        # 交出使用权
    finally:
        conn.close()      # 请求结束后由框架触发，只此一处
```

其他地方（路由层、业务层）**一律不要写 `conn.close()`**。
（历史教训：曾在 `deps.py` 里顺手关闭了共享连接，导致路由层在已关闭的连接上执行 SQL，报 `Cannot operate on a closed database`。FastAPI 的依赖默认有缓存，同一请求里多个 `Depends(get_db)` 拿到的是**同一个**连接对象。）

---

## 二、接口设计规范

1. **路径用名词复数，方法表示动作**：`GET /api/tickets`、`POST /api/tickets`
   ❌ `/api/getTickets`、`/api/createTicket`
2. **业务动作单独成路径**：`POST /api/tickets/{id}/approve`
   （CRUD 表达不了"审批"这种伴随副作用与状态流转的动作）
3. **统一分页参数**：`page`（≥1）、`size`（1–100）
4. **响应信封统一**：成功 `{code, message, data}`
5. **状态码语义要准**：401 未认证 / 403 无权限 / 404 不存在 / 422 参数错 / 400 业务规则不满足

---

## 三、安全规范（每条都有真实教训）

### 3.1 权限三原则

| 原则 | 说明 |
|---|---|
| **默认拒绝（fail-closed）** | 白名单授权；未列举的角色一律"看不到任何数据"。**绝不写"兜底放行"** |
| **身份只来自 token** | 请求体里的 `user_id` 一律不可信（防 IDOR / 水平越权） |
| **功能权限 + 数据权限双层** | 角色能按这个按钮（403）+ 这张数据归不归你管（403）。**只做第一层是最常见的漏洞** |

```python
def apply_scope(where, params, viewer):
    """行级权限的唯一入口：所有查询工单的 SQL 都必须经过它"""
    role = viewer["role"]
    if role == "admin":
        return where, params
    if role == "manager":
        return where + " AND u.department = ?", params + [viewer["department"]]
    if role in ("employee", "finance"):
        return where + " AND t.user_id = ?", params + [viewer["id"]]
    return where + " AND 1 = 0", params     # 未知角色 → 恒空
```

> **为什么兜底必须拒绝？** 新增一个角色（如 `auditor`）时，fail-open 会让它**自动获得全量数据权限**，
> 不报错、不告警，可能几年后才发现。fail-closed 则会让它"什么都看不到"，第一天就有人来问，
> 于是有人显式写下授权——那行代码会被 review、被记录。
> **fail-closed 的失败是"响的"，fail-open 的失败是"哑的"。**

### 3.2 密码与凭证

- 密码只存 **bcrypt 哈希**（自带随机盐），永不存明文，永不用 MD5
- `SECRET_KEY`、`LLM_API_KEY` 只放 `.env`，且 `.env` 必须同时被 `.gitignore` 和 `.dockerignore` 排除
- 密钥**运行时注入**，绝不烘焙进镜像
- 认证失败（用户不存在 / 密码错误）返回**完全相同**的信息，防用户名枚举

### 3.3 数据出境

调用外部服务（尤其是大模型）前，必须已完成权限校验：

```
❌ 拼好提示词（含工单内容）→ 再查权限     （数据已经出去了，撤不回来）
✅ 先查权限 → 通过了才拼提示词 → 才发送
```

### 3.4 SQL 安全

```python
conn.execute("... WHERE id = ?", (tid,))        # ✅ 参数化
conn.execute(f"... WHERE id = '{tid}'")         # ❌ SQL 注入
```

### 3.5 前端安全

- 任何用户输入进 `innerHTML` 前必须转义（`escapeHtml`），防 XSS
- 收到 401 统一 `logout()` 回登录页
- **隐藏按钮只是用户体验，不是安全措施**——安全边界永远在后端

---

## 四、AI 协作规范

### 4.1 分工原则

| 环节 | 交给 AI | 自己必须盯 |
|---|---|---|
| 脚手架 | 建项目、目录结构 | 分层是否符合规范 |
| 写 CRUD | 按表结构生成接口与页面 | **权限过滤有没有漏、SQL 是否参数化** |
| 写样式 | 布局与组件 | 交互是否符合业务 |
| 排错 | 给排查方向 | **自己验证原因**（AI 常猜错） |
| 写文档 | 初稿 | 核对真实性 |
| 方案选型 | 给 2–3 个方案对比 | **自己拍板** |

**一句话**：AI 做重复劳动与初稿，人做判断、边界与兜底。**它写得越快，我审得越细。**

### 4.2 审查 AI 生成代码的七个检查点

1. **边界** — 空输入 / 超长输入 / 不存在的 id / 0 条数据 / 并发同时提交，会崩吗？
2. **注入** — SQL 是参数化还是拼字符串？用户输入直接进 HTML 了吗？
3. **权限** — 有没有校验登录？有没有过滤数据范围？**← AI 最常漏的一条**
4. **异常** — 外部调用（尤其大模型）失败/超时有没有兜底？
5. **日志** — 出问题能不能查到是谁、何时、什么参数？
6. **密钥** — Key 是否被硬编码？**← AI 生成代码的第二高危区**
7. **残留** — 粘贴新版本后，旧函数/旧 id/旧 script 块删干净了吗？

### 4.3 提示词资产管理

- 提示词**存文件**（`prompts/`），不硬编码在 Python 字符串里
- 理由：① 改提示词不用改代码 ② 进 git 可 diff、可 review、可回滚 ③ 可复用、可沉淀
- **提示词的修改属于系统行为变更，应走与代码相同的审查流程**

---

## 五、错误处理与日志

```python
@router.post("/{ticket_id}/approve")
def approve(...):
    try:
        ...
    except BizError as e:
        # 业务异常：语义明确，直接翻译成状态码，可安全暴露给调用方
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception:
        # 未知异常：记录完整堆栈，对外只给通用提示
        logger.exception("审批失败")
        raise HTTPException(status_code=500, detail="审批失败，请查看服务端日志")
```

| 原则 | 说明 |
|---|---|
| 分层兜底 + 底层留真 | 对外不泄漏内部实现；服务端日志必须记录原始异常 |
| 异常详情不外泄 | 异常字符串可能包含文件路径、SQL、表结构 |
| 关键动作留痕 | 状态变更必须写 `ticket_logs`（谁、何时、做了什么、为什么） |

---

## 六、测试规范

| 类型 | 工具 | 说明 |
|---|---|---|
| 零依赖回归 | `python verify_all.py` | 只需标准库，任何环境可跑，覆盖权限/审批/AI 安全 |
| 单元/集成 | `pytest` + `TestClient` | 标准做法；测试库与开发库隔离 |
| 接口冒烟 | `test.ps1` | 铁三角检查 + 多身份对照 + AI 验收 |

### 6.1 差分测试（权限类功能必用）

```python
# ❌ 绝对断言：只测一个身份，权限漏洞照样通过
assert resp.json()["data"]["total"] > 0

# ✅ 差分断言：不同身份的可见集合必须不同
assert seen["zhangsan"] != seen["wangwu"]
assert seen["unknown_role"] == set()
```

> **每个测试都要问：我这次固定了哪些维度？被固定的维度就是没被测的维度。**
> 权限测试里最容易被固定的维度是"**谁在看**"——只用一个账号测，权限漏洞必然漏掉。

### 6.2 回归测试

**每个修过的 BUG 都要沉淀成一条测试**，否则它会以同样的方式回来：

| 测试 | 锁定的历史缺陷 |
|---|---|
| `test_unknown_role_sees_nothing` | 权限兜底放行（fail-open） |
| `test_create_ignores_body_user_id` | 身份取自请求体（IDOR） |
| `test_approve_cross_department_forbidden` | 只有功能权限、漏了数据权限 |
| `test_ask_with_tool_call_and_complete_history` | Function Calling 历史缺环 |

### 6.3 测试数据卫生

- 测试用**临时数据库**，不要污染开发库
- 避免每跑一次就往生产库插一条脏数据（本项目的 `test.ps1` 曾在这一点上有缺陷：每次运行都会新增一张"毒工单"）

---

## 七、Git 规范

1. **提交前必查**：`git status` 里不应出现 `.env`、`*.db`、`__pycache__`
2. `.gitignore` **只防未来，不治历史**——已被追踪的文件要先 `git rm --cached <file>`
3. 提交信息用动词开头并说明范围：`fix: 权限默认拒绝`、`feat: AI 问答助手`、`docs: 部署说明`
4. **密钥一旦进入远程仓库，必须立即轮换**（不是删掉文件就完事——历史里还在）

---

## 八、命名与代码风格

| 对象 | 规范 | 示例 |
|---|---|---|
| 模块/文件 | 小写下划线 | `ticket_service.py` |
| 类 | 大驼峰 | `TicketCreate`、`BizError` |
| 函数/变量 | 小写下划线 | `list_tickets`、`current_user` |
| 常量 | 全大写下划线 | `ALLOWED_TRANSITIONS`、`DB_PATH` |
| 布尔 | 以 `is_` / `has_` 开头 | `is_deleted` |

- 数据库字段用 `snake_case`；表名用复数
- 状态值存**英文**（`pending`），展示层翻译成中文——程序判断用英文，人看用中文
- 3 个参数以上的函数调用**一律用关键字传参**（从语法上免疫位置错位）

---

## 九、三层元规则（所有规范的来源）

1. **凡是靠人反复记住的规则，早晚被漏掉** → 收敛到一处（权限入口、连接管理、配置注入）
2. **凡是靠人手工搬运的数据，早晚被弄脏** → 自动化（脚本登录、机器传递 token）
3. **单个文件正确 ≠ 组装后正确；静默失败最危险** → 组装后真跑一遍 + 产物数量核对

> 新规范应该能回答："它把哪条规则从'人的记忆'搬到了'系统的机制'里？"
> 答不上来的规范，大概率只是口号。
