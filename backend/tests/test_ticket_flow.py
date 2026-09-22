"""工单流转（状态机闭环）与权限边界测试

对应本轮加固项：
  · 状态机闭环：approve / reject / close 三种动作，终态不可再动
  · 动作由请求体指定，非法动作被 schema 拦在门口（422）
  · admin 豁免部门限制；部门为空的账号一律拒绝
  · 不能处理自己提交的工单
  · 工单详情与流转日志接口：越权与不存在都返回 404（防资源枚举）
"""
import pytest


def _new_pending(client, auth, user="zhangsan"):
    resp = client.post("/api/tickets", headers=auth(user),
                       json={"title": f"流转测试-{user}", "content": "内容"})
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


# ══════════════════════════════════════════════
#  状态机闭环
# ══════════════════════════════════════════════

def test_reject_moves_to_rejected(client, auth):
    tid = _new_pending(client, auth, "zhangsan")
    resp = client.post(f"/api/tickets/{tid}/action", headers=auth("lisi"),
                       json={"action": "reject", "remark": "不符合规定"})
    assert resp.status_code == 200
    assert resp.json()["data"]["new_status"] == "rejected"


def test_close_after_approve(client, auth):
    tid = _new_pending(client, auth, "zhangsan")
    client.post(f"/api/tickets/{tid}/action", headers=auth("lisi"), json={"action": "approve"})
    resp = client.post(f"/api/tickets/{tid}/action", headers=auth("lisi"), json={"action": "close"})
    assert resp.status_code == 200
    assert resp.json()["data"]["new_status"] == "closed"


def test_rejected_is_terminal(client, auth):
    """终态不可再流转 —— 证明状态机不是半张表"""
    tid = _new_pending(client, auth, "zhangsan")
    client.post(f"/api/tickets/{tid}/action", headers=auth("lisi"), json={"action": "reject"})
    resp = client.post(f"/api/tickets/{tid}/action", headers=auth("lisi"), json={"action": "close"})
    assert resp.status_code == 400


def test_illegal_action_rejected_by_schema(client, auth):
    """动作取值由 Literal 约束，写错在门口就被拦下（422），不会静默落库"""
    tid = _new_pending(client, auth, "zhangsan")
    resp = client.post(f"/api/tickets/{tid}/action", headers=auth("lisi"),
                       json={"action": "delete_everything"})
    assert resp.status_code == 422


# ══════════════════════════════════════════════
#  权限边界
# ══════════════════════════════════════════════

def test_cannot_act_on_own_ticket(client, auth):
    """主管不能处理自己提交的工单（独立性要求）"""
    tid = _new_pending(client, auth, "lisi")
    resp = client.post(f"/api/tickets/{tid}/action", headers=auth("lisi"), json={"action": "approve"})
    assert resp.status_code == 403
    assert "自己" in resp.json()["message"]


def test_admin_exempt_from_department_check(client, auth):
    """admin 的功能权限与数据权限都放开（否则管理员会批不了任何单）"""
    tid = _new_pending(client, auth, "wangwu")        # 财务部的单
    resp = client.post(f"/api/tickets/{tid}/action", headers=auth("admin1"),
                       json={"action": "approve", "remark": "管理员处理"})
    assert resp.status_code == 200
    assert resp.json()["data"]["new_status"] == "approved"


def test_manager_cannot_act_cross_department(client, auth):
    tid = _new_pending(client, auth, "wangwu")
    resp = client.post(f"/api/tickets/{tid}/action", headers=auth("lisi"), json={"action": "approve"})
    assert resp.status_code == 403


# ══════════════════════════════════════════════
#  详情与日志
# ══════════════════════════════════════════════

def test_ticket_detail_visible_to_owner(client, auth):
    tid = _new_pending(client, auth, "zhangsan")
    resp = client.get(f"/api/tickets/{tid}", headers=auth("zhangsan"))
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == tid


def test_ticket_detail_hides_existence(client, auth):
    """越权访问返回 404 而不是 403 —— 不暴露"这条数据存在"这一事实"""
    tid = _new_pending(client, auth, "wangwu")
    assert client.get(f"/api/tickets/{tid}", headers=auth("lisi")).status_code == 404
    assert client.get("/api/tickets/999999", headers=auth("lisi")).status_code == 404


def test_ticket_logs_show_operator_and_remark(client, auth):
    tid = _new_pending(client, auth, "zhangsan")
    client.post(f"/api/tickets/{tid}/action", headers=auth("lisi"),
                json={"action": "approve", "remark": "同意办理"})
    resp = client.get(f"/api/tickets/{tid}/logs", headers=auth("zhangsan"))
    assert resp.status_code == 200
    logs = resp.json()["data"]
    assert logs[0]["action"] == "submit"
    assert any(l["action"] == "approve" and l["operator"] == "lisi" and l["remark"] == "同意办理"
               for l in logs)


# ══════════════════════════════════════════════
#  输入校验
# ══════════════════════════════════════════════

def test_blank_title_rejected(client, auth):
    """全空格标题应当被拒（原先 min_length=1 会放过它）"""
    resp = client.post("/api/tickets", headers=auth("zhangsan"),
                       json={"title": "   ", "content": "x"})
    assert resp.status_code == 422


def test_invalid_status_filter_rejected(client, auth):
    """status 查询参数有枚举约束，乱写不再静默返回空列表"""
    resp = client.get("/api/tickets?status=whatever", headers=auth("zhangsan"))
    assert resp.status_code == 422
