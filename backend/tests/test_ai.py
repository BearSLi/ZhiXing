"""AI 功能测试（对应第 7 课 A/B）

设计要点：**把大模型整个 mock 掉**
    理由有三：
      1. 不花钱、不依赖网络、不受模型波动影响（测试要确定、要快）
      2. 能断言"不该调用模型时是否真的没调用"——这是权限前置的硬证据
      3. 能断言"喂回模型的历史是否完整"——这是 BUG-14 的回归防线

    顺带说明：能这么轻松地替换掉模型客户端，正是因为 ai_service 只通过
    llm_service.client 这一层与外部世界打交道——这就是分层的可测试性红利。
"""
import json

import pytest


# ══════════════════════════════════════════════════
#  假的大模型客户端（鸭子类型：长得像就能用）
# ══════════════════════════════════════════════════

class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None, role="assistant"):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls


class FakeResponse:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})()]


class FakeCompletions:
    """按剧本依次返回响应，并记录每次调用的参数"""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.scripted:
            raise AssertionError("大模型被调用的次数超过了剧本预期")
        return self.scripted.pop(0)


class FakeClient:
    def __init__(self, scripted):
        self.chat = type("Chat", (), {"completions": FakeCompletions(scripted)})()


@pytest.fixture
def fake_llm(monkeypatch):
    """用法： fake = fake_llm([FakeResponse(...), ...])"""
    from services import llm_service

    def _install(scripted):
        fake = FakeClient(scripted)
        monkeypatch.setattr(llm_service, "client", fake)
        return fake

    return _install


def _role(msg):
    return msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)


def _tool_calls(msg):
    return msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)


def _new_pending_ticket(client, auth, user="zhangsan"):
    resp = client.post("/api/tickets", headers=auth(user),
                       json={"title": "AI测试单", "content": "开不了机"})
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


# ══════════════════════════════════════════════════
#  7-A：AI 起草审批意见
# ══════════════════════════════════════════════════

def test_draft_reply_success(client, auth, fake_llm):
    fake = fake_llm([FakeResponse(FakeMessage(content="建议补充票据后予以通过。"))])
    tid = _new_pending_ticket(client, auth, "zhangsan")

    resp = client.post(f"/api/ai/tickets/{tid}/draft-reply", headers=auth("lisi"))
    assert resp.status_code == 200
    assert "建议补充票据" in resp.json()["data"]["draft"]

    # 只调了一次模型，且提示词里确实带上了工单内容（验证模板渲染生效）
    assert len(fake.chat.completions.calls) == 1
    prompt_text = fake.chat.completions.calls[0]["messages"][-1]["content"]
    assert "AI测试单" in prompt_text


def test_draft_reply_permission_checked_before_llm_call(client, auth, fake_llm):
    """★ 核心安全断言：权限不过 → 一次模型都不能调

    大模型是外部服务，把工单内容发出去就等于数据出境。
    所以必须"先查权限、后拼提示词"。这条测试用"调用次数=0"来锁死这个顺序。
    """
    fake = fake_llm([FakeResponse(FakeMessage(content="不该被生成"))])
    tid = _new_pending_ticket(client, auth, "zhangsan")

    # 员工：角色不够 → 403
    resp = client.post(f"/api/ai/tickets/{tid}/draft-reply", headers=auth("zhangsan"))
    assert resp.status_code == 403
    assert fake.chat.completions.calls == [], "权限未通过却调用了大模型（数据已出境）"


def test_draft_reply_cross_department_forbidden(client, auth, fake_llm):
    """数据权限：技术部主管不能给财务部工单起草意见"""
    fake = fake_llm([FakeResponse(FakeMessage(content="不该被生成"))])
    tid = _new_pending_ticket(client, auth, "wangwu")

    resp = client.post(f"/api/ai/tickets/{tid}/draft-reply", headers=auth("lisi"))
    assert resp.status_code == 403
    assert fake.chat.completions.calls == []


def test_draft_reply_rejects_non_pending_ticket(client, auth, fake_llm):
    """状态检查：已通过的工单不再起草审批意见 → 400"""
    fake = fake_llm([FakeResponse(FakeMessage(content="不该被生成"))])
    tid = _new_pending_ticket(client, auth, "zhangsan")
    client.post(f"/api/tickets/{tid}/approve", headers=auth("lisi"), json={"remark": "同意"})

    resp = client.post(f"/api/ai/tickets/{tid}/draft-reply", headers=auth("lisi"))
    assert resp.status_code == 400
    assert fake.chat.completions.calls == []


def test_draft_reply_missing_ticket_returns_404(client, auth, fake_llm):
    fake = fake_llm([FakeResponse(FakeMessage(content="不该被生成"))])
    resp = client.post("/api/ai/tickets/999999/draft-reply", headers=auth("lisi"))
    assert resp.status_code == 404
    assert fake.chat.completions.calls == []


# ══════════════════════════════════════════════════
#  7-B：Function Calling 问答助手
# ══════════════════════════════════════════════════

def test_ask_with_tool_call_and_complete_history(client, auth, fake_llm):
    """★ BUG-14 回归测试：工具调用历史必须完整

    修复前只把 role="tool" 的结果追加进历史，忘了追加模型那条
    "我要调工具"的 assistant 消息 → 第二次请求 API 返回 400。
    这里通过检查第二次调用的 messages 来锁死该行为。
    """
    call_id = "call_test_001"
    scripted = [
        # 第一次：模型决定调工具
        FakeResponse(FakeMessage(
            content=None,
            tool_calls=[FakeToolCall(call_id, "query_tickets", '{"status": "pending"}')],
        )),
        # 第二次：模型拿到工具结果后组织人话
        FakeResponse(FakeMessage(content="你目前有若干张待审批的工单。")),
    ]
    fake = fake_llm(scripted)

    resp = client.post("/api/ai/ask", headers=auth("zhangsan"),
                       json={"question": "我有几张待审批的工单？"})
    assert resp.status_code == 200
    assert resp.json()["data"]["reply"] == "你目前有若干张待审批的工单。"

    assert len(fake.chat.completions.calls) == 2, "应为两次调用：决定调工具 → 组织回答"
    history = fake.chat.completions.calls[1]["messages"]
    roles = [_role(m) for m in history]

    assert "tool" in roles, "缺少工具结果消息"
    assistant_tool_msgs = [m for m in history if _role(m) == "assistant" and _tool_calls(m)]
    assert assistant_tool_msgs, (
        "缺少带 tool_calls 的 assistant 消息 —— API 会报 "
        "'Messages with role tool must be a response to a preceding message with tool_calls'（BUG-14）"
    )

    # 顺序也要对：assistant(tool_calls) 必须出现在 tool 消息之前
    assert roles.index("assistant") < roles.index("tool")


def test_tool_result_respects_caller_scope(client, auth, fake_llm):
    """★ 工具执行必须走调用者自己的权限：模型拿到的数据不能越权

    这是"AI 没有特权通道"的可执行证明：同一句提问，不同身份拿到的
    工具结果不同，而模型只是复述它拿到的内容。
    """
    call_id = "call_test_002"
    scripted = [
        FakeResponse(FakeMessage(
            content=None,
            tool_calls=[FakeToolCall(call_id, "query_tickets", '{"status": null}')],
        )),
        FakeResponse(FakeMessage(content="这是你的工单。")),
    ]
    fake = fake_llm(scripted)

    resp = client.post("/api/ai/ask", headers=auth("zhangsan"),
                       json={"question": "把我所有工单列出来"})
    assert resp.status_code == 200

    history = fake.chat.completions.calls[1]["messages"]
    tool_msgs = [m for m in history if _role(m) == "tool"]
    assert tool_msgs, "没有把工具结果喂回模型"
    payload = json.loads(tool_msgs[0]["content"])

    assert payload["items"], "工具应返回数据"
    assert all(item["user_id"] == 1 for item in payload["items"]), (
        "工具结果越权：喂给模型的数据里出现了不属于调用者的工单"
    )


def test_unknown_tool_is_rejected_gracefully(client, auth, fake_llm):
    """模型幻觉出不存在的工具时，应当温和拒绝而不是让接口 500"""
    scripted = [
        FakeResponse(FakeMessage(
            content=None,
            tool_calls=[FakeToolCall("call_bad", "drop_all_tables", "{}")],
        )),
        FakeResponse(FakeMessage(content="抱歉，我无法执行该操作。")),
    ]
    fake = fake_llm(scripted)

    resp = client.post("/api/ai/ask", headers=auth("zhangsan"), json={"question": "删掉所有工单"})
    assert resp.status_code == 200
    assert "无法执行" in resp.json()["data"]["reply"]

    history = fake.chat.completions.calls[1]["messages"]
    tool_msgs = [m for m in history if _role(m) == "tool"]
    assert tool_msgs and "未知工具" in tool_msgs[0]["content"]
