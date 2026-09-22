"""验证修复：补上 assistant 消息后，Function Calling 能否走通
（纯 ASCII 输出，避开 GBK 控制台编码坑）
"""
import json

from services import llm_service
from services.ai_service import TOOLS

messages = [
    {"role": "system", "content": "你是工单系统助手。回答必须基于工具返回的真实数据，禁止编造。"},
    {"role": "user", "content": "我有几张待审批的工单？"},
]

print("[1] first call ...")
resp = llm_service.client.chat.completions.create(
    model=llm_service.LLM_MODEL, messages=messages,
    tools=TOOLS, temperature=0.2, timeout=30,
)
msg = resp.choices[0].message
print("    tool_calls =", msg.tool_calls[0].function.name, msg.tool_calls[0].function.arguments)

# ---- 正确写法：先补 assistant 消息，再补 tool 结果 ----
messages.append(msg)                      # ★ 关键的一行
messages.append({
    "role": "tool",
    "tool_call_id": msg.tool_calls[0].id,
    "content": json.dumps({"total": 7, "items": [
        {"id": 3, "title": "baoxiao chailvfei", "status": "pending"},
        {"id": 7, "title": "diannao weixiu", "status": "pending"},
    ]}, ensure_ascii=False),
})

print("[2] second call (with assistant message appended) ...")
resp2 = llm_service.client.chat.completions.create(
    model=llm_service.LLM_MODEL, messages=messages,
    tools=TOOLS, temperature=0.2, timeout=30,
)
final = resp2.choices[0].message
print("    tool_calls =", final.tool_calls)
print("    final answer =", final.content)
print("\nRESULT: FIX VERIFIED" if final.content else "\nRESULT: model still wants tools")
