"""最小复现：Function Calling 第二次调用为什么 500
目的：把 chat_with_tickets 的 bug 单独拎出来，脱离 FastAPI 复现
"""
import json

from services import llm_service
from services.ai_service import TOOLS

messages = [
    {"role": "system", "content": "你是工单系统助手。回答必须基于工具返回的真实数据。"},
    {"role": "user", "content": "我有几张待审批的工单？"},
]

print("=== 第 1 次调用（把问题+工具说明书发给模型） ===")
resp = llm_service.client.chat.completions.create(
    model=llm_service.LLM_MODEL,
    messages=messages,
    tools=TOOLS,
    temperature=0.2,
    timeout=30,
)
msg = resp.choices[0].message
print("模型返回 tool_calls:", msg.tool_calls if msg.tool_calls else "（无，直接说话了）")

if msg.tool_calls:
    tc = msg.tool_calls[0]
    print("模型要求: 调用", tc.function.name, "参数", tc.function.arguments)

    # ══ 复现 bug：只追加 tool 结果，【没有】追加模型的 assistant 消息 ══
    messages.append({
        "role": "tool",
        "tool_call_id": tc.id,
        "content": json.dumps({"total": 5, "items": ["示例工单"]}, ensure_ascii=False),
    })

    print("\n=== 第 2 次调用（复现当前代码的写法） ===")
    try:
        resp2 = llm_service.client.chat.completions.create(
            model=llm_service.LLM_MODEL,
            messages=messages,
            tools=TOOLS,
            temperature=0.2,
            timeout=30,
        )
        print("居然成功了:", resp2.choices[0].message.content)
    except Exception as e:
        print("❌ 失败！异常类型:", type(e).__name__)
        print("   异常内容:", str(e)[:500])

    # ══ 正确写法：补上 assistant 消息再试 ══
    print("\n=== 第 3 次调用（正确写法：先补 assistant 消息） ===")
    messages_fixed = messages[:-1]          # 去掉刚才那条 tool 消息
    messages_fixed.append(msg)              # ★ 补上模型自己的"我要调工具"这条消息
    messages_fixed.append(messages[-1])     # 再把 tool 结果放回去
    try:
        resp3 = llm_service.client.chat.completions.create(
            model=llm_service.LLM_MODEL,
            messages=messages_fixed,
            tools=TOOLS,
            temperature=0.2,
            timeout=30,
        )
        print("✅ 成功！模型最终回答:", resp3.choices[0].message.content)
    except Exception as e:
        print("❌ 仍然失败:", type(e).__name__, str(e)[:300])
