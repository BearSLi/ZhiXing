from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import SECRET_KEY, TOKEN_EXPIRE_HOURS

#密码哈希
def hash_password(plain: str) -> str:
    """明文密码 → bcrypt 哈希（自带随机盐，同一密码每次结果都不同）"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

#密码验证
def verify_password(plain: str, hashed: str) -> bool:
    """把用户输入的明文再哈希一次，和库里的比对"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # 库里的哈希格式不合法（比如还是占位符）——视为验证失败，而不是让程序崩掉
        return False

#签发JWT
def create_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "sub": str(user_id),      # JWT 惯例：sub = 这张 token 属于谁
        "username": username,
        "role": role,             # 6-C 课做权限直接用它
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    """验签 + 解码。签名不对/已过期 → 抛异常，由调用方处理"""
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])