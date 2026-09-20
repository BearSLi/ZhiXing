from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import tickets, auth
import logging

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="工单系统 API", version="0.2.0")
app.include_router(auth.router)

# ⚠️ 加在 include_router 之前
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 开发阶段先全放开；上线必须改成具体域名！
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tickets.router)

@app.get("/")
def root():
    return {"message": "服务已启动", "docs": "/docs"}