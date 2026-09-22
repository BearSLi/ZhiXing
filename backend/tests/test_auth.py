"""认证相关测试（对应第 6 课 A）

覆盖：登录成功 / 密码错误 / 用户不存在 / 无 token / 伪造 token
重点：认证失败的返回必须"看不出区别"（防用户名枚举）
"""


def test_login_success(client):
    resp = client.post("/api/auth/login", json={"username": "lisi", "password": "123456"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["user"]["role"] == "manager"


def test_login_wrong_password_returns_401(client):
    resp = client.post("/api/auth/login", json={"username": "lisi", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user_returns_same_message(client):
    """防用户名枚举：'用户不存在' 与 '密码错误' 必须返回完全相同的响应"""
    wrong_pwd = client.post("/api/auth/login", json={"username": "lisi", "password": "wrong"})
    no_user = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong"})
    assert wrong_pwd.status_code == no_user.status_code == 401
    assert wrong_pwd.json() == no_user.json(), "两种失败必须无法区分，否则可被枚举用户名"


def test_protected_endpoint_without_token(client):
    resp = client.get("/api/tickets")
    assert resp.status_code == 401


def test_protected_endpoint_with_forged_token(client):
    """签名不对的 token 必须被拒（JWT 靠签名防篡改）"""
    resp = client.get("/api/tickets", headers={"Authorization": "Bearer not.a.real.token"})
    assert resp.status_code == 401
