import sqlite3
from datetime import datetime

conn = sqlite3.connect("app.db")
cur = conn.cursor()
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#先写明文占位，后面改成哈希
cur.executemany(
    "INSERT INTO users (username, password_hash, role, department, created_at) VALUES (?,?,?,?,?)",
    [
        ("zhangsan", "hash_placeholder_1", "employee", "技术部", now),
        ("lisi",     "hash_placeholder_2", "manager",  "技术部", now),
        ("wangwu",   "hash_placeholder_3", "finance",  "财务部", now),
    ]
)

cur.executemany(
    """INSERT INTO tickets (title, content, status, user_id, created_at)
       VALUES (?,?,?,?,?)""",
    [
        ("电脑开不了机", "早上来就这样了", "pending",  1, now),
        ("申请门禁卡",   "旧卡丢了",       "approved", 1, now),
        ("报销差旅费",   "出差北京3天",    "pending",  1, now),
    ]
)

cur.executemany(
    """INSERT INTO ticket_logs (ticket_id, action, operator_id, remark, created_at)
       VALUES (?,?,?,?,?)""",
    [
        (1, "submit",  1, None,        now),
        (2, "submit",  1, None,        now),
        (2, "approve", 2, "同意",      now),
    ]
)

conn.commit()
print("假数据插入完成")
