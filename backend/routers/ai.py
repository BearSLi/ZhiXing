"""AI 路由：起草审批意见 + 问答助手

异常处理说明：BizError 由 main.py 的全局处理器统一翻译成 HTTP 响应，
这里不再逐个 try/except —— 抛出去即可，既少写样板代码，也不会把
"业务校验失败"误报成"服务不可用"。
"""
import logging

from fastapi import APIRouter, Depends

from database import get_db
from deps import get_current_user, require_role
from schemas import AskData, AskRequest, DraftData, Ok
from services import ai_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI 助手"])


@router.post(
    "/tickets/{ticket_id}/draft-reply",
    response_model=Ok[DraftData],
    summary="AI 起草审批意见",
)
def draft_reply(
    ticket_id: int,
    conn=Depends(get_db),
    current_user=Depends(require_role("manager", "admin")),
):
    """为待审批工单起草一条审批意见。

    **权限与状态校验发生在调用大模型之前**：大模型是外部服务，
    把工单内容发过去就意味着数据出境，顺序反了就无法撤回。
    """
    result = ai_service.draft_reply(conn, ticket_id, current_user)
    return {"code": 0, "message": "ok", "data": result}


@router.post("/ask", response_model=Ok[AskData], summary="AI 问答助手（可查工单数据）")
def ask(
    payload: AskRequest,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """用自然语言查询工单。

    模型只能调用白名单里的只读工具，且工具以**当前用户身份**执行查询，
    因此 AI 能看到的范围恒等于该用户自身的权限范围。
    """
    result = ai_service.chat_with_tickets(conn, payload.question, current_user)
    return {"code": 0, "message": "ok", "data": result}
