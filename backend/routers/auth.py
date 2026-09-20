from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import get_db
from services import auth_service

router = APIRouter(prefix="/api/auth", tags=["认证"])

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=72)

@router.post("/login")
def login(payload: LoginRequest, conn=Depends(get_db)):
    row = conn.execute(
        """SELECT id, username, password_hash, role
           FROM users WHERE username = ? AND is_deleted = 0""",
        (payload.username,),
    ).fetchone()

    # 安全细节：用户不存在 和 密码错误，返回同一句话（为什么？留作思考题）
    if row is None or not auth_service.verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = auth_service.create_token(row["id"], row["username"], row["role"])
    return {
        "code": 0,
        "message": "登录成功",
        "data": {
            "token": token,
            "user": {"id": row["id"], "username": row["username"], "role": row["role"]},
        },
    }

