"""认证与授权依赖

- get_current_user：认证（你是谁）。验 token → 查库确认账号仍有效 → 返回用户信息
- require_role：授权（你能干什么）。角色门禁工厂，用法 require_role("manager", "admin")

这里抛 HTTPException 是合适的：本模块的职责就是"把认证结果翻译成 HTTP 语义"，
而业务层（services/）只抛 BizError，由全局处理器统一转换。
"""
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from database import get_db
from services import auth_service

# tokenUrl：告诉 /docs "去哪个接口拿 token"，这样文档页会自动出现 Authorize 按钮。
# 必须指向 **表单式** 的 /token（不是 JSON 的 /login）——Swagger 按 OAuth2 规范发的是
# application/x-www-form-urlencoded，指向 JSON 接口会导致 Authorize 报 422。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def get_current_user(token: str = Depends(oauth2_scheme), conn=Depends(get_db)) -> dict:
    # ① 没带 Authorization 头 → OAuth2PasswordBearer 已经自动抛 401，到不了这里

    # ② 验签 + 解码。过期与伪造是两种情况，分开给提示便于前端区分处理
    try:
        payload = auth_service.decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的登录凭证")

    # ③ token 有效 ≠ 用户还在：查一遍库，确认账号没被删除或禁用
    #    类比：token 是"过期的照片"，数据库是"现在的户口本"
    user = conn.execute(
        """SELECT id, username, role, department
           FROM users WHERE id = ? AND is_deleted = 0""",
        (int(payload["sub"]),),
    ).fetchone()

    if user is None:
        raise HTTPException(status_code=401, detail="账号不存在或已被禁用")

    # ④ 返回普通 dict，供业务层当作"当前用户"使用
    return dict(user)


def require_role(*allowed_roles: str):
    """角色门禁工厂：require_role("manager", "admin") = 只放行这两种角色

    工厂模式的好处：一次定义，按需发卡。新增"仅财务可打款"的接口时，
    只需写 Depends(require_role("finance"))，不必复制鉴权逻辑。
    """
    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"需要角色 {'/'.join(allowed_roles)}，你是 {current_user['role']}",
            )
        return current_user

    return checker
