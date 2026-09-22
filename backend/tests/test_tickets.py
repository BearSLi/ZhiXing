"""工单与权限测试（对应第 6 课 B/C）

这里有几条测试是**专门用来锁死已修 BUG 的回归测试**：
  - test_unknown_role_sees_nothing        → 锁 BUG-13（fail-open 权限漏洞）
  - test_create_ignores_body_user_id      → 锁"身份来自 token 而非请求体"（反 IDOR）
  - test_approve_cross_department_forbidden → 锁"功能权限+数据权限双层检查"
"""


# ══════════════════════════════════════════════════
#  数据权限（行级）：不同角色看到的集合必须不同
# ══════════════════════════════════════════════════

def test_employee_sees_only_own_tickets(client, auth):
    resp = client.get("/api/tickets?size=50", headers=auth("zhangsan"))
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert items, "zhangsan 应该有工单"
    assert all(t["user_id"] == 1 for t in items), "员工只能看到自己的工单"


def test_manager_sees_department_tickets(client, auth):
    """主管看到本部门全部（技术部 = zhangsan 的工单）

    断言写成"语义断言"而不是精确计数：测试库里可能有其他用例新建的工单，
    精确计数会随执行顺序漂移，语义断言（都属于本部门）才稳定。
    """
    resp = client.get("/api/tickets?size=50", headers=auth("lisi"))
    items = resp.json()["data"]["items"]
    assert len(items) >= 2, "技术部应有工单"
    assert all(t["submitter"] == "zhangsan" for t in items), "主管只能看到本部门（技术部）的工单"


def test_finance_sees_only_own_tickets(client, auth):
    """财务按当前策略=只看自己的（若将来放开，改这条测试并说明原因）"""
    resp = client.get("/api/tickets?size=50", headers=auth("wangwu"))
    items = resp.json()["data"]["items"]
    assert len(items) >= 1
    assert all(t["user_id"] == 3 for t in items), "财务当前策略为：只能看到自己的工单"


def test_unknown_role_sees_nothing(client, auth):
    """★ BUG-13 回归测试：未列举的角色必须"默认拒绝"，而不是"默认放行"

    修复前的实现用 `return where, params` 兜底 → 任何新角色（如 auditor）
    会自动获得全量数据权限。这条测试保证该漏洞不再出现。
    """
    resp = client.get("/api/tickets?size=50", headers=auth("auditor1"))
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0, "未知角色必须看不到任何数据（fail-closed）"


def test_scope_is_differential(client, auth):
    """差分测试：断言的不是绝对数量，而是"不同身份看到的结果必须不同"

    为什么需要它：只测单一身份（happy path）时，权限漏洞不会暴露——
    zhangsan 自己查自己永远是"对的"。只有横向对比三个视角，才能发现
    "所有人都看到同一批数据"这种覆盖漏洞。
    """
    seen = {}
    for user in ("zhangsan", "lisi", "wangwu", "auditor1"):
        resp = client.get("/api/tickets?size=50", headers=auth(user))
        seen[user] = {t["id"] for t in resp.json()["data"]["items"]}

    assert seen["zhangsan"] != seen["wangwu"], "员工与财务的可见集合不应相同"
    assert seen["auditor1"] == set(), "未知角色可见集合必须为空"
    assert seen["lisi"] >= seen["zhangsan"], "主管应覆盖本部门员工的可见范围"


# ══════════════════════════════════════════════════
#  创建工单：身份只能来自 token
# ══════════════════════════════════════════════════

def test_create_ticket_uses_token_identity(client, auth):
    resp = client.post(
        "/api/tickets", headers=auth("wangwu"),
        json={"title": "测试用-财务提单", "content": "回归测试"},
    )
    assert resp.status_code == 201
    ticket_id = resp.json()["data"]["id"]
    assert ticket_id, "创建接口必须返回新工单 id（曾因缺 return 返回 null）"

    # 复核：确实以 wangwu(user_id=3) 的身份落库
    detail = client.get("/api/tickets?size=50", headers=auth("wangwu")).json()["data"]["items"]
    created = [t for t in detail if t["id"] == ticket_id]
    assert created and created[0]["user_id"] == 3


def test_create_ignores_body_user_id(client, auth):
    """★ 反 IDOR：请求体里塞 user_id 也必须被忽略（身份只认 token）

    修复前 TicketCreate 含 user_id 字段 → 用 zhangsan 的 token 可以
    以任意人的名义建单（水平越权）。
    """
    resp = client.post(
        "/api/tickets", headers=auth("zhangsan"),
        json={"title": "测试用-伪造身份", "content": "试图冒充 wangwu", "user_id": 3},
    )
    assert resp.status_code == 201
    ticket_id = resp.json()["data"]["id"]

    # wangwu 不应该看到这张单（因为它属于 zhangsan）
    wangwu_items = client.get("/api/tickets?size=50", headers=auth("wangwu")).json()["data"]["items"]
    assert ticket_id not in [t["id"] for t in wangwu_items], "请求体里的 user_id 被采信了（IDOR 漏洞）"

    # zhangsan 应该能看到（它确实记在他名下）
    zs_items = client.get("/api/tickets?size=50", headers=auth("zhangsan")).json()["data"]["items"]
    assert ticket_id in [t["id"] for t in zs_items]


# ══════════════════════════════════════════════════
#  审批：功能权限 + 数据权限 + 状态机
# ══════════════════════════════════════════════════

def _make_pending_ticket(client, auth, user="zhangsan"):
    resp = client.post("/api/tickets", headers=auth(user),
                       json={"title": f"审批测试-{user}", "content": "回归"})
    return resp.json()["data"]["id"]


def test_approve_forbidden_for_employee(client, auth):
    """功能权限：员工不是 manager/admin → 403（门禁在路由层拦截）"""
    tid = _make_pending_ticket(client, auth, "zhangsan")
    resp = client.post(f"/api/tickets/{tid}/approve", headers=auth("zhangsan"),
                       json={"remark": "员工越权"})
    assert resp.status_code == 403
    assert "manager" in resp.json()["detail"]


def test_approve_success_by_manager(client, auth):
    tid = _make_pending_ticket(client, auth, "zhangsan")
    resp = client.post(f"/api/tickets/{tid}/approve", headers=auth("lisi"),
                       json={"remark": "同意"})
    assert resp.status_code == 200
    assert resp.json()["data"]["new_status"] == "approved"


def test_approve_twice_rejected_by_state_machine(client, auth):
    """状态机：已 approved 的工单不能再次 approve → 400"""
    tid = _make_pending_ticket(client, auth, "zhangsan")
    client.post(f"/api/tickets/{tid}/approve", headers=auth("lisi"), json={"remark": "同意"})
    resp = client.post(f"/api/tickets/{tid}/approve", headers=auth("lisi"), json={"remark": "再批一次"})
    assert resp.status_code == 400


def test_approve_missing_ticket_returns_404(client, auth):
    """不存在的工单：先查存在性 → 404（而不是 403 或 500）"""
    resp = client.post("/api/tickets/999999/approve", headers=auth("lisi"), json={"remark": "幽灵"})
    assert resp.status_code == 404


def test_approve_cross_department_forbidden(client, auth):
    """★ 数据权限：技术部主管不能审批财务部的工单 → 403

    这条测试锁的是"只做功能权限、漏做数据权限"这个最常见的安全缺陷。
    """
    tid = _make_pending_ticket(client, auth, "wangwu")   # 财务部的单子
    resp = client.post(f"/api/tickets/{tid}/approve", headers=auth("lisi"),
                       json={"remark": "跨部门越权"})
    assert resp.status_code == 403
    assert "本部门" in resp.json()["detail"]
