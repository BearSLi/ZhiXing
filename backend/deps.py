import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from database import get_db
from services import auth_service
from typing import Optional

# tokenUrl：告诉 /docs "去哪个接口拿 token"，这样 /docs 页面会自动出现 Authorize 按钮
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), conn=Depends(get_db)):
    # ① 没带 Authorization 头 → OAuth2PasswordBearer 已经自动抛 401，到不了这里

    # ② 验签 + 解码
    try:
        payload = auth_service.decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的登录凭证")

    # ③ token 有效 ≠ 用户还在：查一遍库，确认账号没被删
    user = conn.execute(
        """SELECT id, username, role, department
           FROM users WHERE id = ? AND is_deleted = 0""",
        (int(payload["sub"]),),
    ).fetchone()

    if user is None:
        raise HTTPException(status_code=401, detail="账号不存在或已被禁用")

    # ④ 把"当前用户"作为 dict 返回 —— 它会被注入到业务函数里
    return dict(user)

def require_role(*allowed_roles: str):
    """按角色发门禁卡：require_role("manager", "admin") = 只放行这两种人"""
    def checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"需要角色 {'/'.join(allowed_roles)}，你是 {current_user['role']}",
            )
        return current_user
    return checker