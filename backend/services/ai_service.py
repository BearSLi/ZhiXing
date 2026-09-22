import json
from pathlib import Path

from services.ticket_service import list_tickets
from services import llm_service
from services.llm_service import chat
from services.ticket_service import BizError

PROMPT_DIR = Path(__file__).parent.parent / "prompts"   # backend/prompts/

# services/ai_service.py 里新增

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_tickets",
            "description": "查询工单列表。可按状态筛选。返回当前用户权限范围内的工单。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "approved", "rejected", "closed"],
                        "description": "工单状态。用户问'待审批'就是 pending，'已通过'就是 approved。",
                    },
                },
                "required": [],
            },
        },
    }
]


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

def chat_with_tickets(conn, user_message: str, current_user: dict) -> dict:
    """AI 助手主循环：模型决定调什么工具，我的代码执行，结果喂回去。"""
    messages = [
        {"role": "system", "content": (
            "你是工单系统助手。回答必须基于工具返回的真实数据，"
            "禁止编造数量或内容。如果工具结果为空，就说没有。"
        )},
        {"role": "user", "content": user_message},
    ]

    for _ in range(3):   # 最多循环 3 轮，防死循环（模型可能连续要工具）
        resp = llm_service.client.chat.completions.create(
            model=llm_service.LLM_MODEL,
            messages=messages,
            tools=TOOLS,
            temperature=0.2,
            timeout=30,
        )
        msg = resp.choices[0].message

        # ── 分岔点：模型想调工具？还是想说话了？ ──
        if not msg.tool_calls:
            return {"reply": msg.content}          # 模型说话了 → 结束

        # ★★ 关键：把模型这条"我要调工具"的消息也存进历史。
        # API 要求 role="tool" 的消息必须紧跟在带 tool_calls 的 assistant 消息之后，
        # 缺了它就会 400: "Messages with role 'tool' must be a response to
        #                      a preceding message with 'tool_calls'"
        messages.append(msg)  

        # 模型要调工具 → 我来执行（每个 tool_call 执行一次）
        for tc in msg.tool_calls:
            if tc.function.name == "query_tickets":
                args = json.loads(tc.function.arguments)     # 模型填的参数（JSON 字符串）

                # ★ 权限闸在这里：viewer=current_user → list_tickets 体内过 apply_scope
                result = list_tickets(
                    conn,
                    viewer=current_user,                     # ← lisi 就是 lisi，AI 也冒充不了
                    status=args.get("status"),
                    page=1,
                    size=50,
                )
                tool_output = result.model_dump()

                # 把工具结果作为 role="tool" 消息喂回模型
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_output, ensure_ascii=False),
                })
            else:
                # 未知工具：模型幻觉出一个不存在的函数名 → 拒绝，别崩
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": "未知工具"}, ensure_ascii=False),
                })

    return {"reply": "（查询轮次超限，请换个问法）"}



