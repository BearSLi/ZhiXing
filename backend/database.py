import sqlite3

DB_PATH = "app.db"

def get_db():
    """FastAPI yield 依赖：请求开始时创建连接，响应结束后自动关闭"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn          # ← 走到这儿停住，把 conn 交出去给请求用
    finally:
        conn.close()        # ← 响应生成完毕后，FastAPI 自动回到这里执行