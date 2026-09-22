"""工单路由：只负责收参数、调服务、返回响应（不写 SQL、不写业务规则）"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from database import get_db
from deps import get_current_user, require_role
from schemas import (
    ActionResult,
    IdData,
    Ok,
    TicketActionRequest,
    TicketCreate,
    TicketLogOut,
    TicketOut,
    TicketPage,
    TicketStatus,
)
from services import ticket_service

router = APIRouter(prefix="/api/tickets", tags=["工单"])


# ══════════════════════════════════════════════
#  查询
# ══════════════════════════════════════════════

@router.get("", response_model=Ok[TicketPage], summary="查询工单列表")
def list_tickets(
    status: Optional[TicketStatus] = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    size: int = Query(20, ge=1, le=100, description="每页条数，最多 100"),
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """结果按当前用户的数据权限自动过滤。

    调用方不需要（也不应该）传"我要看谁的"——数据范围由服务端根据登录身份决定：
    员工=自己的、主管=本部门的、admin=全部、未知角色=空。
    """
    result = ticket_service.list_tickets(
        conn, viewer=current_user, status=status, page=page, size=size
    )
    return {"code": 0, "message": "ok", "data": result.model_dump()}


@router.get("/{ticket_id}", response_model=Ok[TicketOut], summary="查询工单详情")
def get_ticket(
    ticket_id: int,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """单条查询同样经过行级权限过滤。

    越权与不存在都返回 404 —— 不告诉调用方"这条数据存在但你看不到"，
    否则攻击者可以用状态码差异枚举出系统里有哪些工单。
    """
    ticket = ticket_service.get_ticket(conn, ticket_id, current_user)
    return {"code": 0, "message": "ok", "data": ticket.model_dump()}


@router.get("/{ticket_id}/logs", response_model=Ok[List[TicketLogOut]], summary="查询工单流转历史")
def get_ticket_logs(
    ticket_id: int,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """谁、何时、做了什么动作、留下了什么意见"""
    logs = ticket_service.list_ticket_logs(conn, ticket_id, current_user)
    return {"code": 0, "message": "ok", "data": [log.model_dump() for log in logs]}


# ══════════════════════════════════════════════
#  写入
# ══════════════════════════════════════════════

@router.post("", response_model=Ok[IdData], status_code=201, summary="创建工单")
def create_ticket(
    payload: TicketCreate,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """提交人取自 token，**请求体不接受 user_id**。

    否则用别人的 id 就能以他人名义建单（水平越权 / IDOR）。
    本接口不设角色门禁：任何登录用户都可以提交工单，这是业务规则而非疏漏。
    """
    ticket_id = ticket_service.create_ticket(conn, payload, current_user)
    return {"code": 0, "message": "创建成功", "data": {"id": ticket_id}}


@router.post(
    "/{ticket_id}/action",
    response_model=Ok[ActionResult],
    summary="工单流转（通过 / 驳回 / 关闭）",
)
def act_on_ticket(
    ticket_id: int,
    payload: TicketActionRequest,
    conn=Depends(get_db),
    current_user=Depends(require_role("manager", "admin")),
):
    """对工单执行一个流转动作，动作由请求体的 action 指定。

    三层校验：角色门禁（manager/admin）→ 数据权限（本部门，admin 豁免）
    → 独立性（不能处理自己提交的）→ 状态机（当前状态是否允许该动作）。
    并用条件更新 + rowcount 判定兜住并发重复处理。
    """
    result = ticket_service.act_on_ticket(
        conn, ticket_id, payload.action, current_user, payload.remark
    )
    return {"code": 0, "message": "处理完成", "data": result.model_dump()}


@router.post(
    "/{ticket_id}/approve",
    response_model=Ok[ActionResult],
    summary="审批工单（兼容路径，等价于 action=approve）",
)
def approve(
    ticket_id: int,
    payload: TicketActionRequest,
    conn=Depends(get_db),
    current_user=Depends(require_role("manager", "admin")),
):
    """保留旧路径以兼容既有前端与脚本；新代码建议使用 /action。"""
    result = ticket_service.act_on_ticket(
        conn, ticket_id, "approve", current_user, payload.remark
    )
    return {"code": 0, "message": "审批完成", "data": result.model_dump()}
