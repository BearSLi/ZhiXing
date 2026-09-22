"""认证路由：只负责收参数、调服务、返回响应"""
from fastapi import APIRouter, Depends

from database import get_db
from schemas import LoginData, LoginRequest, Ok
from services import auth_service

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=Ok[LoginData], summary="登录换取 JWT")
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
