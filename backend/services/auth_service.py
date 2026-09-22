"""认证业务逻辑：密码哈希、密码校验、JWT 签发与解码、登录校验"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import SECRET_KEY, TOKEN_EXPIRE_HOURS
from errors import BizError


def hash_password(plain: str) -> str:
    """明文密码 → bcrypt 哈希（自带随机盐，同一密码每次结果都不同）"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """把用户输入的明文再哈希一次，和库里的比对"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # 库里的哈希格式不合法（比如还是占位符）——视为验证失败，而不是让程序崩掉
        return False


def create_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "sub": str(user_id),      # JWT 惯例：sub = 这张 token 属于谁
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    """验签 + 解码。签名不对/已过期 → 抛异常，由调用方处理"""
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])


def authenticate(conn, username: str, password: str) -> dict:
    """校验用户名密码，成功返回用户信息，失败抛 401。

    安全细节：**"用户不存在"与"密码错误"返回完全相同的结果**。
    若两者可区分，攻击者就能用登录接口批量枚举出系统里有哪些账号
    （用户名枚举攻击），再拿这些账号去别处撞库。
    """
    row = conn.execute(
        """SELECT id, username, password_hash, role, department
           FROM users WHERE username = ? AND is_deleted = 0""",
        (username,),
    ).fetchone()

    if row is None or not verify_password(password, row["password_hash"]):
        raise BizError("用户名或密码错误", code=401)

    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "department": row["department"],
    }
