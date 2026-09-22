"""数据访问层：只负责连接的创建、加固与释放

加固项（每一条都对应 SQLite 的一个真实默认行为）：
  · foreign_keys = ON   —— SQLite 默认【不强制】外键约束，建表时写的 FOREIGN KEY 等于摆设
  · journal_mode = WAL  —— 读写并发更友好（默认 delete 模式写时会阻塞读）
  · busy_timeout = 5000 —— 拿不到写锁时等待 5 秒再报 database is locked，而不是立刻失败
"""
import sqlite3

from config import DB_PATH


def get_db():
    """FastAPI yield 依赖：请求开始时创建连接，响应结束后自动关闭"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn          # 走到这儿停住，把连接交出去给请求用
    finally:
        conn.close()        # 响应生成完毕后由框架回到这里执行，全程只此一处关闭
