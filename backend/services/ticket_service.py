"""工单业务逻辑（不感知 HTTP，只抛 BizError / ConflictError）

本文件承担三件事：
  1. 行级权限的唯一入口 apply_scope
  2. 工单的读写（列表 / 详情 / 创建 / 流转 / 流转日志）
  3. 状态机与并发控制
"""
from datetime import datetime

from errors import BizError, ConflictError
from schemas import (
    ActionResult,
    TicketCreate,
    TicketLogOut,
    TicketOut,
    TicketPage,
)

# ══════════════════════════════════════════════════════════════
#  状态机：每个状态允许哪些动作
#  "查表"而不是 if-else 硬编码 —— 加状态只需改这张表
# ══════════════════════════════════════════════════════════════
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending":  {"approve", "reject"},
    "approved": {"close"},
    "rejected": set(),      # 已驳回：终态
    "closed":   set(),      # 已关闭：终态
}

ACTION_TO_STATUS = {
    "approve": "approved",
    "reject":  "rejected",
    "close":   "closed",
}


# ══════════════════════════════════════════════════════════════
#  行级权限：唯一入口
# ══════════════════════════════════════════════════════════════

def apply_scope(where: str, params: list, viewer: dict) -> tuple[str, list]:
    """给查询追加数据范围条件。所有查询工单的 SQL 都必须经过它。

    白名单授权 + 默认拒绝（fail-closed）：
      未列举的角色返回恒假条件，宁可看不到，不可看多了。
    为什么兜底必须"拒绝"：新增角色时，fail-open 会让它自动获得全量权限，
    不报错、不告警；fail-closed 则会让它什么都看不到，第一天就有人来问，
    于是有人显式写下授权 —— 那行代码会被 review、被记录。
    """
    role = viewer["role"]

    if role == "admin":
        return where, params                                            # 显式授权：看全部
    if role == "manager":
        return where + " AND u.department = ?", params + [viewer["department"]]
    if role in ("employee", "finance"):
        return where + " AND t.user_id = ?", params + [viewer["id"]]     # 只看自己的

    return where + " AND 1 = 0", params                                  # 未知角色：恒空


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ══════════════════════════════════════════════════════════════
#  查询
# ══════════════════════════════════════════════════════════════

_TICKET_SELECT = """
    SELECT t.id, t.title, t.content, t.status, t.user_id,
           u.username AS submitter, t.created_at
    FROM tickets t
    JOIN users u ON t.user_id = u.id
"""


def list_tickets(conn, viewer: dict, status=None, page=1, size=20) -> TicketPage:
    where = "WHERE t.is_deleted = 0"
    params: list = []
    if status:
        where += " AND t.status = ?"
        params.append(status)

    where, params = apply_scope(where, params, viewer)

    total = conn.execute(
        f"""SELECT COUNT(*) AS c
            FROM tickets t
            JOIN users u ON t.user_id = u.id
            {where}""",
        params,
    ).fetchone()["c"]

    rows = conn.execute(
        f"""{_TICKET_SELECT}
            {where}
            ORDER BY t.id DESC LIMIT ? OFFSET ?""",
        params + [size, (page - 1) * size],
    ).fetchall()

    return TicketPage(
        items=[TicketOut.model_validate(dict(r)) for r in rows],
        total=total,
        page=page,
        size=size,
    )


def get_ticket(conn, ticket_id: int, viewer: dict) -> TicketOut:
    """查单张工单。权限同样经过 apply_scope —— 单条查询也不能绕过行级权限。

    注意：越权与不存在都返回 404，不告诉调用方"这条数据存在但你看不到"
    （否则攻击者可以用它枚举出系统里有哪些工单）。
    """
    where, params = apply_scope("WHERE t.is_deleted = 0 AND t.id = ?", [ticket_id], viewer)
    row = conn.execute(f"{_TICKET_SELECT} {where}", params).fetchone()
    if row is None:
        raise BizError("工单不存在", code=404)
    return TicketOut.model_validate(dict(row))


def list_ticket_logs(conn, ticket_id: int, viewer: dict) -> list[TicketLogOut]:
    """工单流转历史（谁、何时、做了什么、为什么）"""
    get_ticket(conn, ticket_id, viewer)      # 复用权限校验：看不到工单就看不到日志

    rows = conn.execute(
        """SELECT l.id, l.action, u.username AS operator, l.remark, l.created_at
           FROM ticket_logs l
           JOIN users u ON l.operator_id = u.id
           WHERE l.ticket_id = ?
           ORDER BY l.id ASC""",
        (ticket_id,),
    ).fetchall()
    return [TicketLogOut.model_validate(dict(r)) for r in rows]


# ══════════════════════════════════════════════════════════════
#  写入
# ══════════════════════════════════════════════════════════════

def create_ticket(conn, payload: TicketCreate, current_user: dict) -> int:
    """创建工单。

    提交人一律取自 current_user（来自 token），**不接受请求体传 user_id**——
    否则用别人的 id 就能以他人名义建单（水平越权 / IDOR）。
    """
    now = _now()
    cur = conn.execute(
        """INSERT INTO tickets (title, content, status, user_id, created_at)
           VALUES (?, ?, 'pending', ?, ?)""",
        (payload.title, payload.content, current_user["id"], now),
    )
    ticket_id = cur.lastrowid
    conn.execute(
        """INSERT INTO ticket_logs (ticket_id, action, operator_id, created_at)
           VALUES (?, 'submit', ?, ?)""",
        (ticket_id, current_user["id"], now),
    )
    conn.commit()
    return ticket_id


def act_on_ticket(
    conn,
    ticket_id: int,
    action: str,
    operator: dict,
    remark: str | None = None,
) -> ActionResult:
    """对工单执行一个流转动作（approve / reject / close）。

    三层检查，顺序不能乱：
      ① 数据权限：能不能碰这张单子（admin 豁免部门限制）
      ② 独立性：不能处理自己提交的单子
      ③ 状态机：当前状态是否允许这个动作
    最后用**条件更新 + rowcount 判定**防止并发重复处理（乐观锁）。
    """
    if action not in ACTION_TO_STATUS:
        raise BizError(f"不支持的动作：{action}", code=400)

    ticket = conn.execute(
        """SELECT t.id, t.status, t.user_id, u.department AS owner_department
           FROM tickets t
           JOIN users u ON t.user_id = u.id
           WHERE t.id = ? AND t.is_deleted = 0""",
        (ticket_id,),
    ).fetchone()
    if ticket is None:
        raise BizError("工单不存在", code=404)

    # ── ① 数据权限 ──
    if operator["role"] != "admin":
        # 部门为空时一律拒绝：否则 None != None 为假，会变成 fail-open
        if not operator["department"] or operator["department"] != ticket["owner_department"]:
            raise BizError("只能处理本部门的工单", code=403)

    # ── ② 不能自己处理自己提交的单子 ──
    if operator["id"] == ticket["user_id"]:
        raise BizError("不能处理自己提交的工单", code=403)

    # ── ③ 状态机 ──
    allowed = ALLOWED_TRANSITIONS.get(ticket["status"], set())
    if action not in allowed:
        raise BizError(f"当前状态[{ticket['status']}]不允许 {action}", code=400)

    new_status = ACTION_TO_STATUS[action]
    now = _now()

    # ── ④ 乐观并发控制 ──
    # 不用"先 SELECT 判断、再 UPDATE"：两个并发请求可能都读到 pending、
    # 都通过检查、都写日志（TOCTOU 竞态）。改成把状态写进 WHERE 条件，
    # 由数据库保证"只有一个人能改成功"，再用 rowcount 判定结果。
    cur = conn.execute(
        "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
        (new_status, now, ticket_id, ticket["status"]),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise ConflictError("工单状态已被他人变更，请刷新后重试")

    conn.execute(
        """INSERT INTO ticket_logs (ticket_id, action, operator_id, remark, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (ticket_id, action, operator["id"], remark, now),
    )
    conn.commit()
    return ActionResult(id=ticket_id, action=action, new_status=new_status)


def approve_ticket(conn, ticket_id: int, action: str, operator: dict, remark: str | None = None):
    """兼容旧调用签名的薄封装（历史代码与测试仍在用）。

    新代码请直接用 act_on_ticket。
    """
    result = act_on_ticket(conn, ticket_id, action, operator, remark)
    return {"id": result.id, "action": result.action, "new_status": result.new_status}
