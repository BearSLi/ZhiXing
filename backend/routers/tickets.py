from typing import Optional
from deps import get_current_user, require_role
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from database import get_db
from schemas import TicketCreate
from services import ticket_service
from services.ticket_service import BizError
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tickets", tags = ["工单"])

class ApproveRequest(BaseModel):
    remark: Optional[str] = Field(None, max_length=200)

#统一响应格式的包装器
def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}

@router.get("")
def list_tickets(
    status: Optional[str] = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    conn=Depends(get_db),
    current_user=Depends(get_current_user),        
):
    try:
        result = ticket_service.list_tickets(
            conn,
            viewer=current_user,
            status=status,
            page=page,
            size=size,
)
        return ok(result.model_dump())
    except Exception as e:
        logger.exception("查询工单列表失败")      # ← 会把完整堆栈打到 uvicorn 窗口
        raise HTTPException(status_code=500, detail="查询失败，请查看服务端日志")
    finally:
        conn.close()

@router.post("", status_code=201)
def create_ticket(payload: TicketCreate, 
                  conn=Depends(get_db), 
                  current_user=Depends(get_current_user),):
    try:
        ticket_id = ticket_service.create_ticket(conn, payload, current_user)
        return ok({"id": ticket_id}, "创建成功")
    except BizError as e:
        conn.rollback()
        raise HTTPException(status_code=e.code, detail=e.message)   # 业务异常 → HTTP 状态码
    except Exception as e:
        conn.rollback()
        logger.exception("创建工单失败")
        raise HTTPException(status_code=500, detail="创建失败，请查看服务端日志")

@router.post("/{ticket_id}/approve")
def approve(
    ticket_id: int,
    payload: ApproveRequest,
    current_user=Depends(require_role("manager", "admin")),   # ← 门禁只认这两个角色
    conn=Depends(get_db),
):
    try:
        result = ticket_service.approve_ticket(
            conn, ticket_id, "approve", current_user, payload.remark
        )
        return ok(result, "审批完成")
    except BizError as e:
        raise HTTPException(status_code=e.code, detail=e.message)
    except Exception:
        logger.exception("审批失败")
        raise HTTPException(status_code=500, detail="审批失败，请查看服务端日志")