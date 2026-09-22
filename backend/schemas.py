"""数据契约（Pydantic 模型）：请求与响应的类型定义

这里的每个模型都会被 FastAPI 写进 OpenAPI 文档，
所以给字段写 description 等于在写接口文档。
"""
from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")

# 状态与动作的取值范围 —— 把"魔法字符串"收敛成类型，写错会在入口就被拦住
TicketStatus = Literal["pending", "approved", "rejected", "closed"]
TicketAction = Literal["approve", "reject", "close"]


# ══════════════════════════════════════════════
#  统一响应信封
# ══════════════════════════════════════════════

class Ok(BaseModel, Generic[T]):
    """成功响应信封：不同接口只需替换 data 的类型"""
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


# ══════════════════════════════════════════════
#  请求模型
# ══════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, description="登录名")
    password: str = Field(..., min_length=1, max_length=72, description="密码（bcrypt 上限 72 字节）")


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="工单标题")
    content: Optional[str] = Field(None, max_length=1000, description="工单内容")

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("标题不能是空白字符")
        return v.strip()


class TicketActionRequest(BaseModel):
    action: TicketAction = Field("approve", description="动作：approve=通过 / reject=驳回 / close=关闭")
    remark: Optional[str] = Field(None, max_length=200, description="处理意见")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=200, description="自然语言问题")


# ══════════════════════════════════════════════
#  响应数据模型
# ══════════════════════════════════════════════

class UserOut(BaseModel):
    id: int
    username: str
    role: str


class LoginData(BaseModel):
    token: str = Field(..., description="JWT，后续请求放在 Authorization: Bearer <token>")
    user: UserOut


class TicketOut(BaseModel):
    id: int
    title: str
    content: Optional[str] = None
    status: str
    user_id: int
    submitter: str
    created_at: str


class IdData(BaseModel):
    id: int


class ActionResult(BaseModel):
    id: int
    action: str
    new_status: str


class TicketLogOut(BaseModel):
    id: int
    action: str
    operator: str
    remark: Optional[str] = None
    created_at: str


class DraftData(BaseModel):
    ticket_id: int
    draft: str


class AskData(BaseModel):
    reply: str


# ══════════════════════════════════════════════
#  分页
# ══════════════════════════════════════════════

class TicketPage(BaseModel):
    """工单分页结果 —— 明确写死类型，避免泛型实例化的兼容问题"""
    items: List[TicketOut]
    total: int
    page: int
    size: int
