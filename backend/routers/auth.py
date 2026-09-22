"""认证路由：只负责收参数、调服务、返回响应

本模块提供两个登录入口，共用同一套校验逻辑：
  · POST /api/auth/login  —— JSON 请求体，供前端与脚本使用
  · POST /api/auth/token  —— OAuth2 表单，供 /docs 页面的 Authorize 按钮使用

为什么要两个：Swagger UI 的 Authorize 按钮按 OAuth2 规范发送
application/x-www-form-urlencoded 表单，而我们的前端发 JSON。
只保留一个必然导致另一边不可用——所以两边都暴露，逻辑复用同一个 service。
"""
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from config import TOKEN_EXPIRE_HOURS
from database import get_db
from schemas import LoginData, LoginRequest, Ok
from services import auth_service

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=Ok[LoginData], summary="登录换取 JWT（JSON）")
def login(payload: LoginRequest, conn=Depends(get_db)):
    """用户名与密码校验通过后签发 JWT。

    安全细节：**"用户不存在"与"密码错误"返回完全相同的信息**，
    避免攻击者用登录接口枚举出系统里有哪些账号（用户名枚举攻击）。
    """
    user = auth_service.authenticate(conn, payload.username, payload.password)
    token = auth_service.create_token(user["id"], user["username"], user["role"])
    return {
        "code": 0,
        "message": "登录成功",
        "data": {
            "token": token,
            "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
        },
    }


@router.post("/token", summary="登录换取 JWT（OAuth2 表单，供 /docs 调试用）")
def login_form(form: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_db)):
    """OAuth2 密码模式的 token 端点，让 /docs 的 Authorize 按钮可以直接登录。

    注意响应形状：**遵循 OAuth2 规范返回顶层 access_token / token_type**，
    不使用本项目的 {code, message, data} 信封——这是协议要求，不是疏漏。
    Swagger 客户端正是靠 access_token 字段来提取并注入 Authorization 头。
    """
    user = auth_service.authenticate(conn, form.username, form.password)
    token = auth_service.create_token(user["id"], user["username"], user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": TOKEN_EXPIRE_HOURS * 3600,
        "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
    }
