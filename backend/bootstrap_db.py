"""一键初始化数据库：建表 + 种子数据 + 设置演示账号密码

设计目标：**幂等**（可反复执行，不会重复灌数据），且**路径跟随环境变量**
  - 数据库文件不存在 → 自动创建（路径来自 DB_PATH，默认 app.db）
  - 表已存在 → 跳过建表（CREATE TABLE IF NOT EXISTS）
  - 已有用户 → 跳过种子数据（不会重复插入）
  - 密码还是占位符 → 设置为演示密码 123456

用法：
    python bootstrap_db.py

为什么把它单独抽出来（而不是继续用 init_db + seed_data + reset_passwords 三个脚本）：
    容器启动时需要"一步到位且可重复"的初始化动作。三个脚本串行执行既啰嗦，
    又各自写死了 "app.db" 路径，无法跟随 DB_PATH 环境变量。
    收敛成一个幂等入口后，本地开发和容器启动用的是同一套逻辑。
"""
import os
import sqlite3
from datetime import datetime

from database import DB_PATH
from services.auth_service import hash_password

DEMO_PASSWORD = "123456"
DEMO_USERS = [
    ("zhangsan", "employee", "技术部"),
    ("lisi",     "manager",  "技术部"),
    ("wangwu",   "finance",  "财务部"),
    ("admin1",   "admin",    "管理部"),      # 演示"看全部"的角色，同时验证 admin 豁免部门检查
]

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      username      TEXT    NOT NULL UNIQUE,
      password_hash TEXT    NOT NULL,
      role          TEXT    NOT NULL DEFAULT 'employee',
      department    TEXT,
      is_deleted    INTEGER NOT NULL DEFAULT 0,
      created_at    TEXT    NOT NULL,
      updated_at    TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tickets (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      title      TEXT    NOT NULL,
      content    TEXT,
      status     TEXT    NOT NULL DEFAULT 'pending',
      user_id    INTEGER NOT NULL,
      is_deleted INTEGER NOT NULL DEFAULT 0,
      created_at TEXT    NOT NULL,
      updated_at TEXT,
      FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ticket_logs (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      ticket_id   INTEGER NOT NULL,
      action      TEXT    NOT NULL,
      operator_id INTEGER NOT NULL,
      remark      TEXT,
      created_at  TEXT    NOT NULL,
      FOREIGN KEY (ticket_id)   REFERENCES tickets(id),
      FOREIGN KEY (operator_id) REFERENCES users(id)
    )
    """,
    # ── 索引：加在"高频出现在 WHERE / JOIN / ORDER BY 的字段"上 ──
    # 权限过滤按 user_id、状态筛选按 status、软删除按 is_deleted、
    # 日志关联按 ticket_id —— 这四个是当前查询的主要入口
    "CREATE INDEX IF NOT EXISTS idx_tickets_user    ON tickets(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_status  ON tickets(status)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_deleted ON tickets(is_deleted)",
    "CREATE INDEX IF NOT EXISTS idx_logs_ticket     ON ticket_logs(ticket_id)",
]


def main():
    # 确保目标目录存在（容器里首次启动时 /app/data 可能还不存在）
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    os.makedirs(db_dir, exist_ok=True)

    print(f"[bootstrap] 目标数据库: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── ① 建表（幂等）──
    for sql in SCHEMA:
        cur.execute(sql)
    conn.commit()
    print("[bootstrap] 表结构就绪：users / tickets / ticket_logs")

    # ── ② 种子数据（仅当用户表为空）──
    user_count = cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if user_count == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.executemany(
            """INSERT INTO users (username, password_hash, role, department, created_at)
               VALUES (?,?,?,?,?)""",
            [(u, hash_password(DEMO_PASSWORD), r, d, now) for u, r, d in DEMO_USERS],
        )
        cur.executemany(
            """INSERT INTO tickets (title, content, status, user_id, created_at)
               VALUES (?,?,?,?,?)""",
            [
                ("电脑开不了机", "早上来就这样了", "pending",  1, now),
                ("申请门禁卡",   "旧卡丢了",       "approved", 1, now),
                ("报销差旅费",   "出差北京3天",    "pending",  1, now),
            ],
        )
        cur.executemany(
            """INSERT INTO ticket_logs (ticket_id, action, operator_id, remark, created_at)
               VALUES (?,?,?,?,?)""",
            [
                (1, "submit",  1, None,   now),
                (2, "submit",  1, None,   now),
                (2, "approve", 2, "同意", now),
            ],
        )
        conn.commit()
        print("[bootstrap] 已写入种子数据（3 个用户 + 3 张工单 + 3 条流转记录）")
    else:
        print(f"[bootstrap] 已有 {user_count} 个用户，跳过种子数据")

    # ── ③ 修正演示账号密码（仅当仍是占位符）──
    # bcrypt 哈希以 $2b$ / $2a$ 开头；占位符不是，据此判断是否需要重置
    fixed = 0
    for username, _role, _dept in DEMO_USERS:
        row = cur.execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row and not row["password_hash"].startswith("$2"):
            cur.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(DEMO_PASSWORD), row["id"]),
            )
            fixed += 1
    if fixed:
        conn.commit()
        print(f"[bootstrap] 已为 {fixed} 个演示账号设置密码：{DEMO_PASSWORD}")

    conn.close()
    print(
        "[bootstrap] 完成。演示账号：zhangsan(员工) / lisi(主管) / "
        f"wangwu(财务) / admin1(管理员)，密码均为 {DEMO_PASSWORD}"
    )


if __name__ == "__main__":
    main()
