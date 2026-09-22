"""配置集中管理：所有环境相关的值都在这里读取，其他模块只 import 常量

两条设计原则：
  1. **配置只有一个入口**——散落各处的 os.getenv 是维护灾难
  2. **关键的缺失要 fail-fast**——密钥没配就拒绝启动，而不是用一个可预测的默认值跑起来
"""
import os

from dotenv import load_dotenv

load_dotenv()   # 从当前工作目录读取 .env

# ── 密钥：缺失或仍是占位符 → 拒绝启动 ──
# 为什么不给默认值：任何"可预测的兜底密钥"都等于没有密钥——
# 攻击者拿到代码就知道默认值，可以离线伪造任意用户的 JWT（包括 role=admin）。
_PLACEHOLDER_HINTS = ("请替换", "dev-only", "change-me", "your-secret")

SECRET_KEY = (os.getenv("SECRET_KEY") or "").strip()
if not SECRET_KEY or any(h in SECRET_KEY for h in _PLACEHOLDER_HINTS):
    raise RuntimeError(
        "\n"
        + "=" * 66 + "\n"
        "SECRET_KEY 未配置，或仍是 .env.example 里的占位符。\n"
        "请生成一个随机密钥并写入 backend/.env：\n"
        '    python -c "import secrets; print(secrets.token_hex(32))"\n'
        "（.env.example 里有完整的配置模板）\n"
        + "=" * 66
    )

TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "12"))

# ── 数据库 ──
# 本地开发用默认值；容器里通过 docker run -e DB_PATH=/app/data/app.db 覆盖
DB_PATH = os.getenv("DB_PATH", "app.db")

# ── 大模型（OpenAI 兼容接口；换供应商只改这三项）──
LLM_API_KEY = (os.getenv("LLM_API_KEY") or "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat").strip()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))                    # 单次调用超时（秒）
LLM_MAX_TOOL_ROUNDS = int(os.getenv("LLM_MAX_TOOL_ROUNDS", "3"))     # 工具调用最大轮数
