"""应用装配层：挂载路由、中间件、全局异常处理

这一层只做装配，不写业务。看懂它就等于看懂了整个服务的骨架。
"""
import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from errors import BizError
from routers import ai, auth, tickets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="工单系统 API",
    version="1.1.0",
    description=(
        "内部工单系统 + AI 助手。\n\n"
        "- 认证：JWT；密码 bcrypt 哈希；认证失败信息不可区分\n"
        "- 授权：功能权限（角色门禁）+ 数据权限（行级过滤，默认拒绝）\n"
        "- AI：权限校验先于模型调用；Function Calling 工具继承调用者权限"
    ),
)

# 开发期放开跨域；上线必须改成具体域名白名单
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════
#  统一错误响应
#  为什么需要：原先成功走 {code, message, data} 信封，失败却走 FastAPI 原生的
#  {detail}，前端不得不处理两种形状。这里统一成一种，同时保留 detail 字段
#  做向后兼容（旧前端与旧测试不用改）。
# ══════════════════════════════════════════════════════════════

def _error_response(status_code: int, message) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": status_code, "message": message, "detail": message, "data": None},
    )


@app.exception_handler(BizError)
async def biz_error_handler(request: Request, exc: BizError):
    """业务异常：语义明确，可以安全地告诉调用方"""
    return _error_response(exc.code, exc.message)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """框架层异常（401 / 403 / 404 / 405 …）统一成同一种形状"""
    return _error_response(exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """参数校验失败：保留 FastAPI 原生的 errors 列表，便于定位具体字段。

    注意必须过一遍 jsonable_encoder：当自定义校验器抛 ValueError 时，
    exc.errors() 里会带 ctx.error 这个**异常对象**，直接塞进 JSONResponse
    会因为无法序列化而报错，最终被兜底成 500（而不是期望的 422）。
    """
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "参数校验失败",
            "detail": jsonable_encoder(exc.errors()),
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底：日志里留完整堆栈，对外只给通用提示。

    为什么不能把异常内容返回：异常字符串里可能带文件路径、SQL、表结构等内部信息。
    """
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return _error_response(500, "服务内部错误，请稍后重试")


# ══════════════════════════════════════════════════════════════
#  路由挂载
# ══════════════════════════════════════════════════════════════

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(ai.router)


@app.get("/", tags=["健康检查"], summary="健康检查")
def root():
    return {"message": "服务已启动", "docs": "/docs", "version": app.version}
