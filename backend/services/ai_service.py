from pathlib import Path

from services.llm_service import chat
from services.ticket_service import BizError

PROMPT_DIR = Path(__file__).parent.parent / "prompts"   # backend/prompts/


def draft_reply(conn, ticket_id: int, operator: dict) -> dict:
    # ── ① 先过权限，和 approve_ticket 一模一样的三层检查 ──
    ticket = conn.execute(
        """SELECT t.id, t.title, t.content, t.status,
                  u.username AS submitter, u.department AS owner_department,
                  t.created_at
           FROM tickets t
           JOIN users u ON t.user_id = u.id
           WHERE t.id = ? AND t.is_deleted = 0""",
        (ticket_id,),
    ).fetchone()
    if ticket is None:
        raise BizError("工单不存在", code=404)
    if operator["department"] != ticket["owner_department"]:
        raise BizError("只能处理本部门的工单", code=403)     # ← 你写过的检查，原样复用
    if ticket["status"] != "pending":
        raise BizError("只能为待审批的工单起草意见", code=400)

    # ── ② 权限过了，才拼提示词、才发数据给模型 ──
    template = (PROMPT_DIR / "draft_reply.txt").read_text(encoding="utf-8")
    prompt = template.format(
        title=ticket["title"],
        content=ticket["content"] or "（无内容）",
        submitter=ticket["submitter"],
        created_at=ticket["created_at"],
    )

    draft = chat([
        {"role": "system", "content": "你是企业内部工单系统的审批助手，输出克制、专业。"},
        {"role": "user", "content": prompt},
    ])
    return {"ticket_id": ticket_id, "draft": draft}