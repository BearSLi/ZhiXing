import sqlite3

from services.auth_service import hash_password

conn = sqlite3.connect("app.db")
cur = conn.cursor()

for username in ("zhangsan", "lisi", "wangwu"):
    cur.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (hash_password("123456"), username),
    )
    print(f"{username} 的密码已设置为 123456")

conn.commit()
