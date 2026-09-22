"""验证两个修复（服务层直测，不经过 HTTP）
1) BUG-13: apply_scope 是否让三个角色的可见范围不同了
2) BUG-14: chat_with_tickets 的 Function Calling 循环是否跑通
"""
import sqlite3

from services.ticket_service import list_tickets
from services.ai_service import chat_with_tickets

conn = sqlite3.connect("app.db")
conn.row_factory = sqlite3.Row

print("=== [1] BUG-13 验证：三个角色的可见工单数 ===")
users = {}
for row in conn.execute("SELECT id, username, role, department FROM users ORDER BY id"):
    u = dict(row)
    users[u["username"]] = u
    result = list_tickets(conn, viewer=u, page=1, size=50)
    print(f"  {u['username']:10s} role={u['role']:9s} -> total = {result.total}")

print("\n=== [2] BUG-14 验证：Function Calling 主循环 ===")
z = users["zhangsan"]
try:
    answer = chat_with_tickets(conn, "我有几张待审批的工单？", z)
    print("  zhangsan 问 '我有几张待审批的工单？'")
    print("  AI 回答:", answer.get("reply"))
except Exception as e:
    print("  仍然失败:", type(e).__name__, str(e)[:300])

conn.close()
