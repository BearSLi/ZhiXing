import sqlite3
conn = sqlite3.connect("app.db")
cur = conn.cursor()

cur.execute("""
    SELECT t.id, u.username, t.title, t.status
    FROM tickets t
    JOIN users u ON t.user_id = u.id
    WHERE u.department = ?

    SELECT t.id, t.title, t.status, u.username, l.action, l.remark
    FROM tickets t
    JOIN users u ON t.user_id = u.id
    LEFT JOIN ticket_logs l ON l.ticket_id = t.id
""", ("技术部",))


for row in cur.fetchall():
    print(row)