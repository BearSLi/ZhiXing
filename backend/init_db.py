import sqlite3
from datetime import datetime 

#链接数据库
conn = sqlite3.connect("app.db")
cur = conn.cursor()

#用户表
cur.execute("""
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
""")

#工单表
cur.execute("""
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
""")

#流转记录表
cur.execute("""
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
""")

conn.commit()

print("建表完成，数据库文件：app.db")

