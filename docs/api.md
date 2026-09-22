# 接口文档（API Reference）

> **在线可交互文档**：启动服务后访问 <http://127.0.0.1:8000/docs>
> 该文档由 FastAPI 依据代码中的类型声明**自动生成**（OpenAPI 规范），
> 与代码永远同步——不存在"代码改了文档没改"的问题。
> 本文件提供的是**约定说明、鉴权方式、错误码**等自动文档不易表达的部分。

---

## 1. 通用约定

### 1.1 基址

```
http://127.0.0.1:8000
```

### 1.2 成功响应格式（统一信封）

```json
{
  "code": 0,
  "message": "ok",
  "data": { }
}
```

| 字段 | 说明 |
|---|---|
| `code` | `0` 表示业务成功；非 0 为业务错误码 |
| `message` | 人类可读的结果描述 |
| `data` | 业务数据；无数据时为 `null` |

**为什么要包一层？** 让调用方能区分「HTTP 成功但业务失败」与「HTTP 本身失败」，前端只需实现一次错误处理逻辑。

### 1.3 错误响应格式

**失败响应与成功响应使用同一种信封形状**，前端只需实现一次错误处理：

```json
{
  "code": 403,
  "message": "只能处理本部门的工单",
  "detail": "只能处理本部门的工单",
  "data": null
}
```

| 字段 | 说明 |
|---|---|
| `code` | 与 HTTP 状态码一致（业务错误码若要细分，可在此扩展如 `40001`） |
| `message` | 统一的可读描述，前端直接展示即可 |
| `detail` | **兼容字段**：保留是为了既有前端与脚本不必改动（契约演进：新字段先加，旧字段保留一版再删） |
| `data` | 固定为 `null` |

参数校验失败（422）时，`detail` 是字段级错误列表（沿用 FastAPI 原生结构）：

```json
{
  "code": 422,
  "message": "参数校验失败",
  "detail": [{ "type": "value_error", "loc": ["body", "title"], "msg": "标题不能是空白字符" }],
  "data": null
}
```

> 由 `main.py` 的四个全局异常处理器统一产出：`BizError` / `HTTPException` /
> `RequestValidationError` / 兜底 `Exception`（兜底时日志留完整堆栈，对外只给通用提示）。

### 1.4 鉴权

除 `POST /api/auth/login` 与 `GET /` 外，所有接口都需要在请求头携带 token：

```
Authorization: Bearer <token>
```

token 由登录接口签发（JWT，默认有效期 12 小时），**payload 可直接解码查看，但无法篡改**（有签名校验）。

| 鉴权失败情况 | 状态码 | 响应 |
|---|---|---|
| 未携带 token | 401 | `{"detail": "Not authenticated"}` |
| token 过期 | 401 | `{"detail": "登录已过期，请重新登录"}` |
| token 被篡改 / 伪造 | 401 | `{"detail": "无效的登录凭证"}` |
| token 有效但账号已删除 | 401 | `{"detail": "账号不存在或已被禁用"}` |
| 身份合法但角色不够 | 403 | `{"detail": "需要角色 manager/admin，你是 employee"}` |

---

## 2. 接口清单

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/` | 无 | 健康检查 |
| POST | `/api/auth/login` | 无 | 登录换取 token |
| GET | `/api/tickets` | 登录 | 查询工单列表（自动按权限过滤） |
| POST | `/api/tickets` | 登录 | 创建工单 |
| GET | `/api/tickets/{id}` | 登录 | 查询工单详情（按权限过滤，越权返回 404） |
| GET | `/api/tickets/{id}/logs` | 登录 | 查询工单流转历史 |
| POST | `/api/tickets/{id}/action` | manager/admin | 工单流转：`approve` / `reject` / `close` |
| POST | `/api/tickets/{id}/approve` | manager/admin | 审批（兼容路径，等价于 `action=approve`） |
| POST | `/api/ai/tickets/{id}/draft-reply` | manager/admin | AI 起草审批意见 |
| POST | `/api/ai/ask` | 登录 | AI 问答助手（可查工单数据） |

**完整状态机**

```
pending ──approve──→ approved ──close──→ closed
   └────reject────→ rejected          （rejected / closed 为终态，不可再流转）
```

动作由请求体的 `action` 指定，取值被 `Literal` 约束：写错的值会在入口被拦成 422，不会静默落库。

---

## 3. 接口详情

### 3.1 健康检查

```
GET /
```
**响应 200**
```json
{ "message": "服务已启动", "docs": "/docs" }
```

---

### 3.2 登录

```
POST /api/auth/login
Content-Type: application/json
```
**请求体**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `username` | string | 是 | 1–50 字符 |
| `password` | string | 是 | 1–72 字符 |

```json
{ "username": "lisi", "password": "123456" }
```

**响应 200**
```json
{
  "code": 0,
  "message": "登录成功",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": { "id": 2, "username": "lisi", "role": "manager" }
  }
}
```

**响应 401**：用户名与密码错误**返回完全相同的信息**，防止攻击者枚举有效用户名。

---

### 3.3 查询工单列表

```
GET /api/tickets?status=pending&page=1&size=20
Authorization: Bearer <token>
```
**查询参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `status` | string | 无 | 按状态筛选：`pending` / `approved` / `rejected` / `closed` |
| `page` | int | 1 | 页码，≥1 |
| `size` | int | 20 | 每页条数，1–100 |

**响应 200**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "id": 3,
        "title": "报销差旅费",
        "content": "出差北京3天",
        "status": "pending",
        "user_id": 1,
        "submitter": "zhangsan",
        "created_at": "2026-09-19 21:23:29"
      }
    ],
    "total": 1,
    "page": 1,
    "size": 20
  }
}
```

> 🔒 **数据权限（本接口的核心）**
> 返回结果会按调用者身份自动过滤，调用方无需也不应该传"我要看谁的"：
>
> | 角色 | 过滤条件 | 效果 |
> |---|---|---|
> | `employee` | `t.user_id = 自己` | 只看自己的工单 |
> | `manager` | `u.department = 自己部门` | 看本部门全部 |
> | `admin` | 无附加条件 | 看全部 |
> | `finance` / 其他已列举角色 | `t.user_id = 自己` | 只看自己的 |
> | **未列举的未知角色** | 恒假条件 | **返回空（fail-closed）** |
>
> 想验证权限是否真的生效？用不同账号调同一接口，比较 `total` 与 `items` 的归属即可（差分验证）。
---

### 3.4 创建工单

```
POST /api/tickets
Authorization: Bearer <token>
Content-Type: application/json
```
**请求体**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `title` | string | 是 | 1–100 字符 |
| `content` | string | 否 | ≤1000 字符 |

```json
{ "title": "打印机卡纸", "content": "三楼打印机" }
```

**响应 201**
```json
{ "code": 0, "message": "创建成功", "data": { "id": 12 } }
```

> 🔒 **提交人取自 token，不取自请求体。**
> 即使请求体里塞 `"user_id": 999` 也会被忽略——身份不能由客户端声明。
> （这类漏洞在 OWASP 里叫 IDOR / 水平越权，是最常见的越权形态之一。）

---

### 3.5 工单流转（审批 / 驳回 / 关闭）

```
POST /api/tickets/{ticket_id}/action
Authorization: Bearer <manager 或 admin 的 token>
Content-Type: application/json
```
**路径参数**：`ticket_id`（int）

**请求体**

| 字段 | 类型 | 必填 | 取值 |
|---|---|---|---|
| `action` | string | 否 | `approve`（默认）/ `reject` / `close` |
| `remark` | string | 否 | ≤200 字符，处理意见 |

```json
{ "action": "reject", "remark": "缺少发票，请补充后重新提交" }
```

**响应 200**
```json
{
  "code": 0,
  "message": "处理完成",
  "data": { "id": 3, "action": "reject", "new_status": "rejected" }
}
```

**错误码**

| 状态码 | 场景 |
|---|---|
| 403 | 角色不是 manager/admin；工单不属于本部门；或试图处理自己提交的工单 |
| 404 | 工单不存在 |
| 400 | 当前状态不允许该动作（状态机拦截，例如对已通过的工单再审批） |
| **409** | **并发冲突**：状态已被他人变更（乐观锁判定失败） |
| 422 | `action` 取值非法（被 schema 拦在门口） |

> 🔒 **本接口做了三层检查，缺一不可**
> 1. **功能权限**（路由层 `require_role`）：你的角色能不能按这个按钮 → 403
> 2. **数据权限**（业务层部门比对，admin 豁免）：这张单子归不归你管 → 403
> 3. **独立性**（业务层）：不能处理自己提交的工单 → 403
>
> 只做第 1 层是很常见的安全缺陷——技术部主管将能审批财务部的工单。
>
> ⚙️ **并发保护**：更新语句把"当前状态"写进 WHERE 条件
> （`UPDATE ... WHERE id=? AND status=?`），再用 `rowcount` 判定是否真的改到，
> 避免"两个主管同时审批"导致重复处理与日志翻倍。

> 兼容路径：`POST /api/tickets/{ticket_id}/approve` 等价于 `action=approve`，供既有前端与脚本使用。

---

### 3.6 查询工单详情

```
GET /api/tickets/{ticket_id}
Authorization: Bearer <token>
```

**响应 200**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "id": 3, "title": "报销差旅费", "content": "出差北京3天", "status": "pending",
    "user_id": 1, "submitter": "zhangsan", "created_at": "2026-09-19 21:23:29"
  }
}
```

> 🔒 **越权与不存在都返回 404**，不告诉调用方"这条数据存在但你看不到"——
> 否则攻击者可以用状态码差异（403 vs 404）枚举出系统里有哪些工单。

---

### 3.7 查询工单流转历史

```
GET /api/tickets/{ticket_id}/logs
Authorization: Bearer <token>
```

**响应 200**
```json
{
  "code": 0,
  "message": "ok",
  "data": [
    { "id": 1, "action": "submit",  "operator": "zhangsan", "remark": null,     "created_at": "2026-09-19 21:23:29" },
    { "id": 5, "action": "approve", "operator": "lisi",     "remark": "同意",   "created_at": "2026-09-20 10:02:11" }
  ]
}
```

权限与详情接口一致：看不到工单就看不到它的日志。

---

---

### 3.8 AI 起草审批意见

```
POST /api/ai/tickets/{ticket_id}/draft-reply
Authorization: Bearer <manager 或 admin 的 token>
```

**响应 200**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "ticket_id": 3,
    "draft": "本工单申请报销北京出差3天的差旅费。建议：需要补充信息。请提供出差审批单、起止日期、交通及住宿票据明细与金额。"
  }
}
```

**响应延迟**：3–10 秒属正常（大模型逐字生成）。

**错误码**：403（角色/部门不符）、404（工单不存在）、400（非待审批状态）、500（模型服务不可用）

> 🔒 **权限检查发生在大模型调用之前。**
> 大模型是外部服务，把工单内容发过去意味着数据出境。
> 必须先确认调用者有权查看该工单，再构造提示词。

---

### 3.9 AI 问答助手（Function Calling）

```
POST /api/ai/ask
Authorization: Bearer <任意已登录用户的 token>
Content-Type: application/json
```
**请求体**

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `question` | string | 是 | 1–200 字符 |

```json
{ "question": "我有几张待审批的工单？" }
```

**响应 200**
```json
{
  "code": 0,
  "message": "ok",
  "data": { "reply": "你目前有 3 张待审批的工单。其中……" }
}
```

**工作流程**

```
问题 + 工具说明书 → 模型
      ↓  模型返回："我要调 query_tickets(status=pending)"
你的代码以【调用者身份】执行查询（走同一套行级权限）
      ↓
查询结果喂回模型 → 模型组织成人话
```

> 🔒 **AI 没有特权通道。**
> 模型能检索到的数据范围，恒等于提问者本人调 `GET /api/tickets` 能看到的范围。
> 因此"让 AI 列出全公司工单"只会得到自己的那些——防线不在提示词里，在 SQL 的 `WHERE` 里。

**安全设计（四层）**

| 层 | 措施 |
|---|---|
| 参数层 | 工具参数的 `enum` 白名单，模型无法填入非法值 |
| 工具层 | 只暴露只读查询，永不向模型暴露写/删接口 |
| 执行层 | 工具查询复用 `list_tickets`，强制经过行级权限 |
| 结构层 | 工单内容作为"数据"（tool 消息）进入模型，与"指令"（system/user）分离 |

---

## 4. 状态码速查

| 状态码 | 含义 | 常见触发点 |
|---|---|---|
| 200 | 成功 | — |
| 201 | 创建成功 | `POST /api/tickets` |
| 400 | 业务规则不满足 | 状态机拦截、参数业务校验 |
| 401 | 未认证 | 缺 token / 过期 / 伪造 / 账号已删 |
| 403 | 已认证但无权限 | 角色不够、跨部门越权 |
| 404 | 资源不存在 | 工单不存在、路径写错 |
| 422 | 参数校验失败 | 缺必填字段、类型不符、超长 |
| 500 | 服务端异常 | 代码异常、模型服务不可用 |

---

## 5. 联调建议（来自本项目踩坑记录）

1. **先测后端再测前端**：用 curl 直连接口，绕开浏览器与跨域干扰，一次只验证一层。
2. **注意 `Content-Type`**：发送 JSON 必须带 `Content-Type: application/json`，否则服务端收不到请求体。
3. **注意编码**：Windows PowerShell 下建议用 `Invoke-WebRequest` + 手动 UTF-8 解码，或直接用 `curl.exe`；否则中文可能显示为乱码（数据本身没坏，是解码方式不对）。
4. **区分"请求"与"响应"**：排查问题时先明确"我发出去的是什么、我收到的是什么"。
5. **token 会过期**：调试脚本每次运行都重新登录，不要手工复制粘贴长 token（容易沾上不可见字符）。
