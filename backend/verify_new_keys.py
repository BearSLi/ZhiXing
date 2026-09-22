"""轮换后的真实链路验证（一次性脚本，跑完可删）

检查三件事：
  1. 配置能被正确加载（fail-fast 通过，新 SECRET_KEY 不是占位符）
  2. 用新 SECRET_KEY 签发/解码 token 正常
  3. 用新 LLM_API_KEY **真实调用一次模型**（只花极少 token）
"""
import sys

print("=== [1] 配置加载 ===")
try:
    from config import LLM_BASE_URL, LLM_MODEL, SECRET_KEY
    print(f"  SECRET_KEY  长度={len(SECRET_KEY)}  （fail-fast 已通过）")
    print(f"  LLM_BASE_URL = {LLM_BASE_URL}")
    print(f"  LLM_MODEL    = {LLM_MODEL}")
except Exception as e:  # noqa: BLE001
    print(f"  ✗ 配置加载失败: {type(e).__name__}: {e}")
    sys.exit(1)

print("\n=== [2] 新 SECRET_KEY 签发与校验 ===")
from services import auth_service

token = auth_service.create_token(1, "zhangsan", "employee")
payload = auth_service.decode_token(token)
assert payload["sub"] == "1" and payload["role"] == "employee"
print(f"  ✓ 签发/解码成功，payload={payload['username']}/{payload['role']}")

print("\n=== [3] 新 LLM_API_KEY 真实调用（最小请求）===")
from services import llm_service

try:
    reply = llm_service.chat(
        [{"role": "user", "content": "只回复两个字：正常"}],
        temperature=0,
    )
    print(f"  ✓ 调用成功，模型返回：{reply.strip()[:60]}")
    print("\n结论：新密钥全部可用，AI 功能可以正常演示。")
except Exception as e:  # noqa: BLE001
    print(f"  ✗ 调用失败: {type(e).__name__}")
    print(f"    {str(e)[:400]}")
    print("\n常见原因：Key 复制不全 / 有空格 / 平台余额不足 / 模型名与供应商不匹配")
    sys.exit(1)
