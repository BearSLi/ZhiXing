"""检查泄露的旧 LLM_API_KEY 是否已被平台吊销（一次性脚本）

原理：从 git 历史里取出旧 Key，用它发一次最小请求。
  · 被拒绝（401/403/无效 Key）→ 说明已吊销或删除，泄露已被控制 ✓
  · 调用成功 → 旧 Key 仍然有效，必须立刻去平台删除 ✗

不打印任何密钥内容。
"""
import re
import subprocess
import sys

# ── 从 git 历史取出旧 Key（不打印）──
try:
    old_env = subprocess.run(
        ["git", "show", "a021854:backend/.env"],
        capture_output=True, text=True, encoding="utf-8", cwd="..",
    ).stdout
except Exception as e:  # noqa: BLE001
    print(f"  无法读取 git 历史: {e}")
    sys.exit(2)

m = re.search(r"(?m)^LLM_API_KEY=(.*)$", old_env)
if not m:
    print("  历史里没有找到 LLM_API_KEY")
    sys.exit(2)

old_key = m.group(1).strip()
print(f"旧 Key 前缀 {old_key[:10]}… 长度 {len(old_key)}（内容不打印）")

# ── 用旧 Key 发一次最小请求 ──
from openai import OpenAI

from config import LLM_BASE_URL, LLM_MODEL

client = OpenAI(api_key=old_key, base_url=LLM_BASE_URL, timeout=20, max_retries=0)
print("\n用【旧 Key】尝试调用模型…")
try:
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=1,
        temperature=0,
    )
    print("  ✗✗ 旧 Key 仍然可用！泄露尚未控制")
    print("     → 立刻去服务商控制台【删除】这个旧 Key（创建新的不等于旧的失效）")
    sys.exit(1)
except Exception as e:  # noqa: BLE001
    name = type(e).__name__
    msg = str(e)[:200]
    if any(k in name for k in ("Authentication", "Permission")) or "401" in msg or "invalid" in msg.lower():
        print(f"  ✓ 旧 Key 已被拒绝（{name}）—— 泄露已控制")
        sys.exit(0)
    print(f"  ? 结果不明确：{name}: {msg}")
    print("     若这是网络/超时问题，请重试；若是余额或权限问题，请人工确认平台状态")
    sys.exit(2)
