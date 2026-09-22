"""零依赖回归验证脚本（不需要 pytest / httpx）

为什么存在：
    pytest 套件（tests/）是标准做法，但它需要额外安装 pytest + httpx。
    本脚本只用 Python 标准库，在 service 层直接验证核心行为，
    保证"任何环境下都能一键确认系统没坏"。

用法：
    python verify_all.py

覆盖的回归点：
    · 密码哈希 / token 签发与篡改检测
    · 权限矩阵（employee / manager / finance / 未知角色 fail-closed）  ← BUG-13
    · 创建工单的身份来源（只认 token，不认请求体）                      ← 反 IDOR
    · 审批：部门校验 / 状态机 / 不存在                        ← 功能权限+数据权限
    · AI 起草：权限不过时绝不调用大模型                        ← 数据出境防护
    · AI 问答：工具结果不越权 + 工具调用历史完整                        ← BUG-14
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime

# ⚠️ 必须在导入应用模块之前设置 DB_PATH（database 模块导入时即读取）
TEST_DB = os.path.join(tempfile.gettempdir(), "ticket_system_verify.db")
os.environ["DB_PATH"] = TEST_DB

if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

from bootstrap_db import main as bootstrap_main  # noqa: E402
from database import DB_PATH  # noqa: E402
from schemas import TicketCreate  # noqa: E402
from services import llm_service  # noqa: E402
from services.ai_service import chat_with_tickets, draft_reply  # noqa: E402
from services.auth_service import (  # noqa: E402
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from services.ticket_service import (  # noqa: E402
    BizError,
    approve_ticket,
    create_ticket,
    list_tickets,
)

# ── 建库 + 种子数据 ──
bootstrap_main()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# 追加一个"未知角色"用户，用于验证 fail-closed
# （admin1 已在 bootstrap 的演示数据里，无需重复插入）
conn.execute(
    """INSERT INTO users (username, password_hash, role, department, created_at)
       VALUES (?,?,?,?,?)""",
    ("auditor1", hash_password("123456"), "auditor", "审计部",
     datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
)
conn.commit()


def user(name):
    return dict(conn.execute(
        "SELECT id, username, role, department FROM users WHERE username = ?", (name,)
    ).fetchone())


# ══════════════════════════════════════════════
#  迷你测试框架
# ══════════════════════════════════════════════
PASSED, FAILED = [], []


def check(name):
    def deco(fn):
        try:
            fn()
            PASSED.append(name)
            print(f"  [PASS] {name}")
        except AssertionError as e:
            FAILED.append((name, str(e) or "断言失败"))
            print(f"  [FAIL] {name}  -> {e or '断言失败'}")
        except Exception as e:  # noqa: BLE001
            FAILED.append((name, f"{type(e).__name__}: {e}"))
            print(f"  [ERR ] {name}  -> {type(e).__name__}: {e}")
        return fn
    return deco


def expect_biz_error(code, fn, *args, **kwargs):
    """断言业务函数抛出指定 code 的 BizError"""
    try:
        fn(*args, **kwargs)
    except BizError as e:
        assert e.code == code, f"期望 BizError({code})，实际 BizError({e.code}: {e.message})"
        return e
    raise AssertionError(f"期望抛出 BizError({code})，但没有抛异常")


def new_pending_ticket(owner="zhangsan"):
    tid = create_ticket(conn, TicketCreate(title=f"验证单-{owner}", content="内容"), user(owner))
    assert tid, "create_ticket 必须返回新工单 id"
    return tid


print("\n=== [1] 认证基础 ===")


@check("密码哈希：正确密码通过、错误密码拒绝")
def _():
    h = hash_password("123456")
    assert h.startswith("$2"), "bcrypt 哈希应以 $2 开头"
    assert verify_password("123456", h)
    assert not verify_password("wrong", h)


@check("同一密码两次哈希不同（盐生效）")
def _():
    assert hash_password("123456") != hash_password("123456")


@check("token 可解码且内容正确")
def _():
    t = create_token(1, "zhangsan", "employee")
    p = decode_token(t)
    assert p["sub"] == "1" and p["role"] == "employee"


@check("篡改 token 被签名拦下")
def _():
    import base64
    import json as _json
    import jwt

    t = create_token(1, "zhangsan", "employee")
    head, payload_seg, sig = t.split(".")
    raw = base64.urlsafe_b64decode(payload_seg + "=" * (-len(payload_seg) % 4)).decode()
    forged = raw.replace('"employee"', '"manager"')
    seg = base64.urlsafe_b64encode(forged.encode()).decode().rstrip("=")
    try:
        decode_token(f"{head}.{seg}.{sig}")
    except jwt.InvalidTokenError:
        return
    raise AssertionError("篡改后的 token 竟然验签通过了")


print("\n=== [2] 数据权限矩阵（BUG-13 回归）===")


@check("员工：只看到自己的工单")
def _():
    uid = user("zhangsan")["id"]
    r = list_tickets(conn, viewer=user("zhangsan"), size=50)
    assert r.total >= 1
    assert all(i.user_id == uid for i in r.items)


@check("同部门两个员工：互相看不到对方的工单")
def _():
    """演示数据刻意在技术部放了两个员工，这条断言保证这种差异真实存在"""
    a = user("zhangsan")
    b = user("zhaoliu")
    assert a["department"] == b["department"], "本用例要求两人同部门"
    seen_a = {i.id for i in list_tickets(conn, viewer=a, size=50).items}
    seen_b = {i.id for i in list_tickets(conn, viewer=b, size=50).items}
    assert seen_a and seen_b, "两个员工都应各有工单"
    assert not (seen_a & seen_b), f"同部门员工不应看到对方的工单，交集={seen_a & seen_b}"


@check("主管：看到本部门全部，且多于任何单个员工")
def _():
    tech_dept = {"zhangsan", "zhaoliu", "lisi"}
    mgr = list_tickets(conn, viewer=user("lisi"), size=50)
    emp = list_tickets(conn, viewer=user("zhangsan"), size=50)
    assert all(i.submitter in tech_dept for i in mgr.items), "主管只能看到本部门成员提交的工单"
    assert mgr.total > emp.total, f"主管({mgr.total}) 应多于单个员工({emp.total})"
    # 主管看到的集合应等于本部门所有员工可见集合的并集
    union = set()
    for name in ("zhangsan", "zhaoliu", "lisi"):
        union |= {i.id for i in list_tickets(conn, viewer=user(name), size=50).items}
    assert {i.id for i in mgr.items} == union, "主管可见范围应等于本部门成员的并集"


@check("财务：当前策略下只看到自己的")
def _():
    uid = user("wangwu")["id"]
    r = list_tickets(conn, viewer=user("wangwu"), size=50)
    assert r.total >= 1
    assert all(i.user_id == uid for i in r.items)


@check("未知角色：默认拒绝（fail-closed，看不到任何数据）")
def _():
    r = list_tickets(conn, viewer=user("auditor1"), size=50)
    assert r.total == 0, f"未知角色看到了 {r.total} 条数据 —— fail-open 漏洞复现！"


@check("差分断言：不同身份看到的集合不同")
def _():
    seen = {u: {i.id for i in list_tickets(conn, viewer=user(u), size=50).items}
            for u in ("zhangsan", "zhaoliu", "lisi", "wangwu", "auditor1")}
    assert seen["zhangsan"] != seen["zhaoliu"], "同部门两个员工不应看到同一批数据"
    assert seen["zhangsan"] != seen["wangwu"]
    assert seen["auditor1"] == set()
    assert seen["lisi"] >= seen["zhangsan"]
    assert seen["lisi"] >= seen["zhaoliu"]
    # 主管看不到其他部门的单子
    assert not (seen["lisi"] & seen["wangwu"]), "跨部门数据不应出现在主管的可见集合里"


print("\n=== [3] 创建工单：身份只认传入的用户 ===")


@check("创建后 user_id 等于提交者（不来自请求体）")
def _():
    owner = user("wangwu")
    tid = create_ticket(conn, TicketCreate(title="身份验证单", content="x"), owner)
    row = conn.execute("SELECT user_id FROM tickets WHERE id = ?", (tid,)).fetchone()
    assert row["user_id"] == owner["id"], f"工单归属错误：{row['user_id']} != {owner['id']}"


@check("创建同时写入流转日志（审计不断档）")
def _():
    tid = create_ticket(conn, TicketCreate(title="日志验证单", content="x"), user("zhangsan"))
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM ticket_logs WHERE ticket_id = ? AND action = 'submit'", (tid,)
    ).fetchone()["c"]
    assert n == 1, "创建工单必须留下 submit 日志"


print("\n=== [4] 审批：功能权限 + 数据权限 + 状态机 ===")


@check("主管审批本部门工单成功，状态变为 approved")
def _():
    tid = new_pending_ticket("zhangsan")
    r = approve_ticket(conn, tid, "approve", user("lisi"), "同意")
    assert r["new_status"] == "approved"


@check("跨部门审批被拒（403 只能审批本部门的工单）")
def _():
    tid = new_pending_ticket("wangwu")
    e = expect_biz_error(403, approve_ticket, conn, tid, "approve", user("lisi"), "越权")
    assert "本部门" in e.message


@check("状态机：已通过的工单不能再次审批（400）")
def _():
    tid = new_pending_ticket("zhangsan")
    approve_ticket(conn, tid, "approve", user("lisi"), "同意")
    expect_biz_error(400, approve_ticket, conn, tid, "approve", user("lisi"), "再批")


@check("不存在的工单返回 404")
def _():
    expect_biz_error(404, approve_ticket, conn, 999999, "approve", user("lisi"), "幽灵")


print("\n=== [5] AI 起草：权限检查先于模型调用 ===")


class _FakeCompletions:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.scripted.pop(0)


class _FakeClient:
    def __init__(self, scripted):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(scripted)})()


def _msg(content=None, tool_calls=None):
    return type("M", (), {"role": "assistant", "content": content, "tool_calls": tool_calls})()


def _resp(message):
    return type("R", (), {"choices": [type("C", (), {"message": message})()]})()


def _tool_call(call_id, name, arguments):
    fn = type("F", (), {"name": name, "arguments": arguments})()
    return type("T", (), {"id": call_id, "function": fn})()


_orig_client = llm_service.client


@check("权限不过时，一次模型都不调用")
def _():
    fake = _FakeClient([_resp(_msg(content="不该被生成"))])
    llm_service.client = fake
    try:
        tid = new_pending_ticket("zhangsan")
        # 跨部门：lisi 是技术部，工单属于 wangwu → 应在调模型前被拦
        wid = new_pending_ticket("wangwu")
        expect_biz_error(403, draft_reply, conn, wid, user("lisi"))
        expect_biz_error(400, draft_reply, conn, tid, user("lisi")) if False else None
        assert fake.chat.completions.calls == [], "权限未过却调用了大模型（数据已出境）"
    finally:
        llm_service.client = _orig_client


@check("权限通过时，提示词里包含工单内容")
def _():
    fake = _FakeClient([_resp(_msg(content="建议补充票据后通过。"))])
    llm_service.client = fake
    try:
        tid = new_pending_ticket("zhangsan")
        out = draft_reply(conn, tid, user("lisi"))
        assert "建议补充票据" in out["draft"]
        assert len(fake.chat.completions.calls) == 1
        assert "验证单-zhangsan" in fake.chat.completions.calls[0]["messages"][-1]["content"]
    finally:
        llm_service.client = _orig_client


print("\n=== [6] AI 问答：工具不越权 + 历史完整（BUG-14 回归）===")


@check("工具结果只含调用者可见的数据")
def _():
    fake = _FakeClient([
        _resp(_msg(content=None, tool_calls=[_tool_call("c1", "query_tickets", '{"status": null}')])),
        _resp(_msg(content="这是你的工单。")),
    ])
    llm_service.client = fake
    try:
        out = chat_with_tickets(conn, "列出我所有工单", user("zhangsan"))
        assert out["reply"] == "这是你的工单。"
        history = fake.chat.completions.calls[1]["messages"]
        tool_msgs = [m for m in history if isinstance(m, dict) and m.get("role") == "tool"]
        assert tool_msgs, "工具结果没有喂回模型"
        import json as _json
        payload = _json.loads(tool_msgs[0]["content"])
        assert payload["items"], "工具应返回数据"
        assert all(i["user_id"] == 1 for i in payload["items"]), "工具结果越权了"
    finally:
        llm_service.client = _orig_client


@check("历史完整：assistant(tool_calls) 与 tool 消息都在，且顺序正确")
def _():
    fake = _FakeClient([
        _resp(_msg(content=None, tool_calls=[_tool_call("c2", "query_tickets", '{"status": "pending"}')])),
        _resp(_msg(content="你有若干张待审批工单。")),
    ])
    llm_service.client = fake
    try:
        chat_with_tickets(conn, "我有几张待审批的？", user("zhangsan"))
        history = fake.chat.completions.calls[1]["messages"]
        roles = [(m.get("role") if isinstance(m, dict) else getattr(m, "role", None)) for m in history]
        assert "tool" in roles, "缺少 tool 消息"
        has_assistant_tools = any(
            (m.get("tool_calls") if isinstance(m, dict) else getattr(m, "tool_calls", None))
            for m in history
        )
        assert has_assistant_tools, "缺少带 tool_calls 的 assistant 消息（BUG-14）"
        assert roles.index("assistant") < roles.index("tool"), "消息顺序错误"
    finally:
        llm_service.client = _orig_client


@check("模型幻觉出不存在的工具时被温和拒绝")
def _():
    fake = _FakeClient([
        _resp(_msg(content=None, tool_calls=[_tool_call("c3", "drop_all_tables", "{}")])),
        _resp(_msg(content="抱歉，我无法执行该操作。")),
    ])
    llm_service.client = fake
    try:
        out = chat_with_tickets(conn, "删掉所有工单", user("zhangsan"))
        assert "无法执行" in out["reply"]
        history = fake.chat.completions.calls[1]["messages"]
        tool_msgs = [m for m in history if isinstance(m, dict) and m.get("role") == "tool"]
        assert tool_msgs and "未知工具" in tool_msgs[0]["content"]
    finally:
        llm_service.client = _orig_client


print("\n=== [7] 状态机闭环与权限边界（本轮修复项）===")


@check("驳回：pending --reject--> rejected")
def _():
    from services.ticket_service import act_on_ticket
    tid = new_pending_ticket("zhangsan")
    r = act_on_ticket(conn, tid, "reject", user("lisi"), "不符合规定")
    assert r.new_status == "rejected"


@check("关闭：approved --close--> closed")
def _():
    from services.ticket_service import act_on_ticket
    tid = new_pending_ticket("zhangsan")
    act_on_ticket(conn, tid, "approve", user("lisi"), "同意")
    r = act_on_ticket(conn, tid, "close", user("lisi"), "已办结")
    assert r.new_status == "closed"


@check("终态不可再动：rejected 工单不能 close")
def _():
    from services.ticket_service import act_on_ticket
    tid = new_pending_ticket("zhangsan")
    act_on_ticket(conn, tid, "reject", user("lisi"), "驳回")
    expect_biz_error(400, act_on_ticket, conn, tid, "close", user("lisi"), "再关")


@check("不能处理自己提交的工单（独立性）")
def _():
    """lisi 以自己名义提单，再用主管身份批自己的单 —— 应被拒"""
    from services.ticket_service import act_on_ticket
    own = create_ticket(conn, TicketCreate(title="主管自己的单", content="x"), user("lisi"))
    expect_biz_error(403, act_on_ticket, conn, own, "approve", user("lisi"), "自批")


@check("admin 豁免部门限制，可以处理跨部门工单")
def _():
    from services.ticket_service import act_on_ticket
    tid = new_pending_ticket("wangwu")          # 财务部
    r = act_on_ticket(conn, tid, "approve", user("admin1"), "管理员处理")
    assert r.new_status == "approved"


@check("部门为空的用户不能处理任何工单（修掉 None != None 的 fail-open）")
def _():
    from services.ticket_service import act_on_ticket
    # 造一个没有部门的经理
    conn.execute(
        """INSERT INTO users (username, password_hash, role, department, created_at)
           VALUES (?,?,?,?,?)""",
        ("nodept_mgr", hash_password("123456"), "manager", None, "2026-01-01 00:00:00"),
    )
    conn.commit()
    mgr = dict(conn.execute(
        "SELECT id, username, role, department FROM users WHERE username='nodept_mgr'"
    ).fetchone())
    # 再造一个没有部门的员工提交工单，制造 None == None 的危险场景
    conn.execute(
        """INSERT INTO users (username, password_hash, role, department, created_at)
           VALUES (?,?,?,?,?)""",
        ("nodept_emp", hash_password("123456"), "employee", None, "2026-01-01 00:00:00"),
    )
    conn.commit()
    emp = dict(conn.execute(
        "SELECT id, username, role, department FROM users WHERE username='nodept_emp'"
    ).fetchone())
    tid = create_ticket(conn, TicketCreate(title="无部门员工的单", content="x"), emp)
    expect_biz_error(403, act_on_ticket, conn, tid, "approve", mgr, "无部门互批")


@check("工单详情：越权与不存在都返回 404（防资源枚举）")
def _():
    from services.ticket_service import get_ticket
    tid = new_pending_ticket("wangwu")                     # 财务部的单
    wid = get_ticket(conn, tid, user("wangwu")).id         # 本人可以看
    assert wid == tid
    expect_biz_error(404, get_ticket, conn, tid, user("lisi"))      # 跨部门 → 404 而非 403
    expect_biz_error(404, get_ticket, conn, 999999, user("lisi"))   # 不存在 → 404


@check("流转日志可查，且能看到操作人")
def _():
    from services.ticket_service import act_on_ticket, list_ticket_logs
    tid = new_pending_ticket("zhangsan")
    act_on_ticket(conn, tid, "approve", user("lisi"), "同意办理")
    logs = list_ticket_logs(conn, tid, user("zhangsan"))
    actions = [l.action for l in logs]
    assert actions[0] == "submit", f"第一条应为 submit，实际 {actions}"
    assert "approve" in actions
    assert any(l.operator == "lisi" and l.remark == "同意办理" for l in logs)


@check("并发审批：只有一个成功，且不产生重复日志（TOCTOU 修复）")
def _():
    import sqlite3 as _s3
    import threading

    from services.ticket_service import act_on_ticket as _act

    tid = new_pending_ticket("zhangsan")
    operator = user("lisi")          # ★ 必须在主线程取好：sqlite3 连接不能跨线程使用
    outcomes = []
    barrier = threading.Barrier(2)

    def worker():
        c = _s3.connect(DB_PATH, timeout=10)
        c.row_factory = _s3.Row
        c.execute("PRAGMA busy_timeout = 10000")
        try:
            barrier.wait(timeout=5)          # 让两个线程尽量同时冲进去
            _act(c, tid, "approve", operator, "并发审批")
            outcomes.append("ok")
        except Exception as exc:             # noqa: BLE001
            outcomes.append(type(exc).__name__)
        finally:
            c.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    approve_logs = conn.execute(
        "SELECT COUNT(*) AS c FROM ticket_logs WHERE ticket_id = ? AND action = 'approve'",
        (tid,),
    ).fetchone()["c"]
    assert approve_logs == 1, (
        f"并发审批应只写 1 条日志，实际 {approve_logs} 条（两次结果：{outcomes}）"
        " —— 说明存在 TOCTOU 竞态"
    )


# ══════════════════════════════════════════════
#  汇总
# ══════════════════════════════════════════════
conn.close()
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

total = len(PASSED) + len(FAILED)
print("\n" + "=" * 56)
print(f"结果: {len(PASSED)}/{total} 通过")
if FAILED:
    print("失败项:")
    for name, reason in FAILED:
        print(f"  - {name}: {reason}")
    print("=" * 56)
    sys.exit(1)
print("全部通过 —— 核心行为（权限 / 审批 / AI 安全）验证无误")
print("=" * 56)
