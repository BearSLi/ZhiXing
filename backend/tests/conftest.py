"""测试夹具：独立测试库 + 登录好的 token

核心设计：**不碰生产的 app.db**
    在导入应用之前先把 DB_PATH 指向一个临时文件，测试跑完就删掉。
    这解决了"每跑一次回归测试就污染一次开发数据"的问题。
"""
import os
import sqlite3
import tempfile
from datetime import datetime

import pytest

# ⚠️ 必须在 import main 之前设置 DB_PATH —— database 模块在导入时就会读取它
TEST_DB = os.path.join(tempfile.gettempdir(), "ticket_system_test.db")
os.environ["DB_PATH"] = TEST_DB

from bootstrap_db import SCHEMA  # noqa: E402
from services.auth_service import hash_password  # noqa: E402
import main  # noqa: E402

DEMO_PASSWORD = "123456"

# 测试数据集：刻意让三类角色看到的集合不同，便于做权限差分断言
#   zhangsan(id=1, employee, 技术部) → 2 张自己的
#   lisi    (id=2, manager,  技术部) → 技术部全部（= zhangsan 的 2 张）
#   wangwu  (id=3, finance,  财务部) → 1 张自己的
#   auditor1(id=4, auditor,  审计部) → 0 张（未知角色必须 fail-closed）
USERS = [
    ("zhangsan", "employee", "技术部"),
    ("lisi",     "manager",  "技术部"),
    ("wangwu",   "finance",  "财务部"),
    ("auditor1", "auditor",  "审计部"),
]

# (title, content, status, user_id)
TICKETS = [
    ("电脑开不了机", "早上来就这样了", "pending",  1),
    ("申请门禁卡",   "旧卡丢了",       "approved", 1),
    ("报销差旅费",   "出差北京3天",    "pending",  3),
]


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_db():
    """建一个干净的测试库（会话级：整套测试共用一个）"""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    conn = sqlite3.connect(TEST_DB)
    for sql in SCHEMA:
        conn.execute(sql)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.executemany(
        """INSERT INTO users (username, password_hash, role, department, created_at)
           VALUES (?,?,?,?,?)""",
        [(u, hash_password(DEMO_PASSWORD), r, d, now) for u, r, d in USERS],
    )
    conn.executemany(
        """INSERT INTO tickets (title, content, status, user_id, created_at)
           VALUES (?,?,?,?,?)""",
        [(t, c, s, uid, now) for t, c, s, uid in TICKETS],
    )
    conn.commit()
    conn.close()

    yield

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture(scope="session")
def client():
    """FastAPI 测试客户端（进程内调用，不走网络）"""
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="session")
def tokens(client):
    """一次性把所有测试账号登录好，返回 {用户名: token}"""
    result = {}
    for username, _role, _dept in USERS:
        resp = client.post(
            "/api/auth/login", json={"username": username, "password": DEMO_PASSWORD}
        )
        assert resp.status_code == 200, f"{username} 登录失败: {resp.text}"
        result[username] = resp.json()["data"]["token"]
    return result


@pytest.fixture
def auth(tokens):
    """用法： client.get(url, headers=auth("lisi"))"""
    def _headers(username: str) -> dict:
        return {"Authorization": f"Bearer {tokens[username]}"}
    return _headers
