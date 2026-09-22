from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from deps import require_role
from services import ai_service
from services.ticket_service import BizError
import logging
from pydantic import BaseModel, Field
from deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI 助手"])

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=200)

@router.post("/tickets/{ticket_id}/draft-reply")
def draft_reply(
    ticket_id: int,
    conn=Depends(get_db),
    current_user=Depends(require_role("manager", "admin")),   # ← 你的门禁工厂，第三次复用
):
    try:
        result = ai_service.draft_reply(conn, ticket_id, current_user)
        return {"code": 0, "message": "ok", "data": result}
    except BizError as e:
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception:
        logger.exception("AI 起草失败")
        raise HTTPException(status_code=500, detail="AI 服务暂时不可用，请稍后再试")

@router.post("/ask")
def ask(
    payload: AskRequest,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),      # ← 只要求登录，人人可用
):
    try:
        result = ai_service.chat_with_tickets(conn, payload.question, current_user)
        return {"code": 0, "message": "ok", "data": result}
    except Exception:
        logger.exception("AI 问答失败")
        raise HTTPException(status_code=500, detail="AI 服务暂时不可用")


