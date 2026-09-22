from datetime import datetime

from schemas import TicketCreate, TicketOut, TicketPage

ALLOWED_TRANSITIONS = {
    # 当前状态  →  允许的动作
    "pending":  {"approve", "reject"},
    "approved": {"close"},
    "rejected": set(),      # 已驳回的不能再动
    "closed":   set(),      # 已关闭的不能再动
}

class BizError(Exception):
    """业务异常：只描述'业务上出了什么问题'，不关心 HTTP"""
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code

def apply_scope(where: str, params: list, viewer: dict) -> tuple[str, list]:
    """统一的行级权限入口。白名单授权 + 默认拒绝（fail-closed）。"""
    role = viewer["role"]

    if role == "admin":
        return where, params                                            # 显式授权：看全部
    if role == "manager":
        return where + " AND u.department = ?", params + [viewer["department"]]
    if role in ("employee", "finance"):
        return where + " AND t.user_id = ?", params + [viewer["id"]]     # 只看自己的

    # ★ 未知角色：默认拒绝。宁可看不到，不可看多了。
    return where + " AND 1 = 0", params

def list_tickets(conn, viewer, status=None, page=1, size=20):
    where = "WHERE t.is_deleted = 0"
    params = []
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
        f"""SELECT t.id, t.title, t.content, t.status, t.user_id,
                   u.username AS submitter, t.created_at
            FROM tickets t
            JOIN users u ON t.user_id = u.id
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

def create_ticket(conn, payload: TicketCreate, current_user: dict):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """INSERT INTO tickets (title, content, status, user_id, created_at)
           VALUES (?, ?, 'pending', ?, ?)""",
        (payload.title, payload.content, current_user["id"], now),   # ← 用 token 里的人
    )
    ticket_id = cur.lastrowid
    conn.execute(
        """INSERT INTO ticket_logs (ticket_id, action, operator_id, created_at)
           VALUES (?, 'submit', ?, ?)""",
        (ticket_id, current_user["id"], now),
    )
    conn.commit()          
    return ticket_id 

def approve_ticket(conn, ticket_id: int, action: str, operator: dict, remark: str = None):
    ticket = conn.execute(
        """SELECT t.id, t.status, t.user_id, u.department AS owner_department
           FROM tickets t
           JOIN users u ON t.user_id = u.id          -- ← 顺着 user_id 把提交人的部门带出来
           WHERE t.id = ? AND t.is_deleted = 0""",
        (ticket_id,),
    ).fetchone()
    if ticket is None:
        raise BizError("工单不存在", code=404)

    # ★ 核心检查：数据范围权限 —— 审批人部门 vs 提交人部门
    if operator["department"] != ticket["owner_department"]:
        raise BizError("只能审批本部门的工单", code=403)

    # 状态机：当前状态允许哪些动作，查表而不是 if-else 硬编码
    allowed = ALLOWED_TRANSITIONS.get(ticket["status"], set())
    if action not in allowed:
        raise BizError(f"当前状态[{ticket['status']}]不允许{action}", code=400)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
        ("approved" if action == "approve" else "rejected", now, ticket_id),
    )
    conn.execute(
        """INSERT INTO ticket_logs (ticket_id, action, operator_id, remark, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (ticket_id, action, operator["id"], remark, now),
    )
    conn.commit()
    return {"id": ticket_id, "action": action, "new_status": "approved" if action == "approve" else "rejected"}
