from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

class ApproveRequest(BaseModel):
    remark: Optional[str] = Field(None, max_length=200)


#请求模型
class TicketCreate(BaseModel):
    title: str = Field(..., min_length = 1, max_length = 100, description= "工单标题")
    content: Optional[str] = Field(None, max_length = 1000, description = "工单内容")

#响应模型
class TicketOut(BaseModel):
    id: int 
    title: str
    content: Optional[str] = None
    status: str
    user_id: int
    submitter: str
    created_at: str

#统一的分页模型
class TicketPage(BaseModel):
    """工单分页结果 —— 明确写死类型，不用泛型"""
    items: List[TicketOut]
    total: int
    page: int
    size: int

