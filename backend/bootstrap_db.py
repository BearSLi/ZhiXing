"""一键初始化数据库：建表 + 种子数据 + 设置演示账号密码

设计目标：**幂等**（可反复执行，不会重复灌数据），且**路径跟随环境变量**
  - 数据库文件不存在 → 自动创建（路径来自 DB_PATH，默认 app.db）
  - 表已存在 → 跳过建表（CREATE TABLE IF NOT EXISTS）
  - 已有用户 → 跳过种子数据（不会重复插入）
  - 密码还是占位符 → 设置为演示密码 123456

用法：
    python bootstrap_db.py            # 幂等初始化（已有数据则跳过）
    python bootstrap_db.py --reset    # 删库重建，得到干净的演示数据

演示数据的设计原则（很重要）：
    数据必须能**体现出权限差异**，否则演示时看不出效果。
    这里刻意安排了：
      · 同一个部门里有【两个员工】→ 员工之间互相看不到对方的单子
      · 主管看到的 = 本部门所有员工的单子 → 数量明显多于任何单个员工
      · 另一个部门的员工 → 主管也看不到他的单子（部门隔离）
    这样"员工 vs 员工 vs 主管"的三方对照才有肉眼可见的区别。

为什么把它单独抽出来（而不是继续用 init_db + seed_data + reset_passwords 三个脚本）：
    容器启动时需要"一步到位且可重复"的初始化动作。三个脚本串行执行既啰嗦，
    又各自写死了 "app.db" 路径，无法跟随 DB_PATH 环境变量。
    收敛成一个幂等入口后，本地开发和容器启动用的是同一套逻辑。
"""
import os
import sqlite3
import sys
from datetime import datetime

from database import DB_PATH
from services.auth_service import hash_password

DEMO_PASSWORD = "123456"

# (用户名, 角色, 部门)
# 注意：故意在"技术部"放两个员工，让"主管比员工看得多"成为可见事实
DEMO_USERS = [
    ("zhangsan", "employee", "技术部"),      # 技术部 · 员工 A
    ("zhaoliu",  "employee", "技术部"),      # 技术部 · 员工 B（与 A 互相看不到对方的单子）
    ("lisi",     "manager",  "技术部"),      # 技术部 · 主管（能看到 A 和 B 的全部）
    ("wangwu",   "finance",  "财务部"),      # 财务部 · 员工（技术部主管看不到他的单子）
    ("admin1",   "admin",    "管理部"),      # 管理员（看全部，且豁免部门检查）
]

# (标题, 内容, 状态, 提交人用户名)
DEMO_TICKETS = [
    # ── 技术部 · zhangsan ──
    ("电脑开不了机",   "早上来就这样了",   "pending",  "zhangsan"),
    ("申请门禁卡",     "旧卡丢了",         "approved", "zhangsan"),
    ("报销差旅费",     "出差北京3天",      "pending",  "zhangsan"),
    # ── 技术部 · zhaoliu（关键：让同部门两个员工的可见集合不同）──
    ("申请压测服务器", "需要一台机器做压测", "pending",  "zhaoliu"),
    ("显示器偶尔黑屏", "外接屏会闪一下",   "pending",  "zhaoliu"),
    # ── 技术部 · lisi 自己提的单（主管也不是全知，自己的单别人看不到）──
    ("申请团队培训预算", "季度技术分享",   "pending",  "lisi"),
    # ── 财务部 · wangwu（部门隔离：技术部主管看不到这张）──
    ("报销办公用品",   "打印纸与墨盒",     "pending",  "wangwu"),
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


def _remove_db_files():
    """删除数据库文件（含 WAL 模式产生的附属文件）"""
    for suffix in ("", "-wal", "-shm"):
        path = DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)
            print(f"[bootstrap] 已删除 {path}")


def main(reset: bool = False):
    if reset:
        print("[bootstrap] --reset：将删除现有数据库并重建")
        _remove_db_files()

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
    print("[bootstrap] 表结构就绪：users / tickets / ticket_logs（含 4 个索引）")

    # ── ② 种子数据（仅当用户表为空）──
    user_count = cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if user_count == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 用户：记下用户名 → id 的映射，供工单引用
        user_ids: dict[str, int] = {}
        for username, role, dept in DEMO_USERS:
            cur.execute(
                """INSERT INTO users (username, password_hash, role, department, created_at)
                   VALUES (?,?,?,?,?)""",
                (username, hash_password(DEMO_PASSWORD), role, dept, now),
            )
            user_ids[username] = cur.lastrowid

        # 工单：逐条插入，同时写一条 submit 流转日志
        ticket_ids: dict[str, int] = {}
        for title, content, status, owner in DEMO_TICKETS:
            cur.execute(
                """INSERT INTO tickets (title, content, status, user_id, created_at)
                   VALUES (?,?,?,?,?)""",
                (title, content, status, user_ids[owner], now),
            )
            tid = cur.lastrowid
            ticket_ids[title] = tid
            cur.execute(
                """INSERT INTO ticket_logs (ticket_id, action, operator_id, created_at)
                   VALUES (?, 'submit', ?, ?)""",
                (tid, user_ids[owner], now),
            )
            # 已通过的工单补一条审批日志，让流转历史看起来完整
            if status == "approved":
                cur.execute(
                    """INSERT INTO ticket_logs (ticket_id, action, operator_id, remark, created_at)
                       VALUES (?, 'approve', ?, ?, ?)""",
                    (tid, user_ids["lisi"], "同意，请按流程办理", now),
                )

        conn.commit()
        print(f"[bootstrap] 已写入演示数据：{len(DEMO_USERS)} 个用户 + {len(DEMO_TICKETS)} 张工单")
    else:
        print(f"[bootstrap] 已有 {user_count} 个用户，跳过种子数据（如需重置请加 --reset）")

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

    # ── ④ 打印可见范围矩阵（让演示者一眼知道该看到什么）──
    print("\n[bootstrap] 权限演示矩阵（同一接口、不同账号的可见条数应当不同）")
    demo_users = cur.execute(
        "SELECT id, username, role, department FROM users ORDER BY id"
    ).fetchall()
    print(f"    {'账号':<10} {'角色':<10} {'部门':<8} 可见工单")
    for u in demo_users:
        if u["role"] == "admin":
            cond, args = "1=1", ()
        elif u["role"] == "manager":
            cond, args = "owner.department = ?", (u["department"],)
        elif u["role"] in ("employee", "finance"):
            cond, args = "t.user_id = ?", (u["id"],)
        else:
            cond, args = "1=0", ()
        n = cur.execute(
            f"""SELECT COUNT(*) FROM tickets t
                JOIN users owner ON t.user_id = owner.id
                WHERE t.is_deleted = 0 AND {cond}""",
            args,
        ).fetchone()[0]
        print(f"    {u['username']:<10} {u['role']:<10} {u['department']:<8} {n} 条")

    conn.close()
    print(
        f"\n[bootstrap] 完成。演示账号密码均为 {DEMO_PASSWORD}：\n"
        "    zhangsan / zhaoliu（技术部员工，互相看不到对方的单子）\n"
        "    lisi（技术部主管，能看到上面两人的全部）\n"
        "    wangwu（财务部，技术部主管看不到他的单子）\n"
        "    admin1（管理员，看全部且可跨部门处理）"
    )


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
