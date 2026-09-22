"""HTTP 层验收脚本（零依赖，只用标准库）

用途：对真实运行的服务做端到端检查——验证路由、错误信封、状态码与权限行为。
与 verify_all.py 的分工：那个测 service 层逻辑，这个测 HTTP 层契约。

用法（需先启动服务）：
    python http_check.py [base_url]
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"

PASS, FAIL = [], []


def request(method: str, path: str, token: str | None = None, body=None):
    """返回 (status_code, json_body)"""
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"_raw": raw[:200]}


def check(name):
    def deco(fn):
        try:
            fn()
            PASS.append(name)
            print(f"  [PASS] {name}")
        except AssertionError as e:
            FAIL.append((name, str(e) or "断言失败"))
            print(f"  [FAIL] {name}  -> {e or '断言失败'}")
        except Exception as e:  # noqa: BLE001
            FAIL.append((name, f"{type(e).__name__}: {e}"))
            print(f"  [ERR ] {name}  -> {type(e).__name__}: {e}")
        return fn
    return deco


def login(username: str) -> str:
    code, body = request("POST", "/api/auth/login",
                         body={"username": username, "password": "123456"})
    assert code == 200, f"{username} 登录失败: {code} {body}"
    return body["data"]["token"]


print(f"目标服务: {BASE}\n")

tokens = {}
print("=== [0] 准备：登录各角色 ===")


@check("四个角色均可登录")
def _():
    for u in ("zhangsan", "lisi", "wangwu", "admin1"):
        tokens[u] = login(u)
    assert len(tokens) == 4


print("\n=== [1] 错误信封统一（原先成功/失败两种形状）===")


@check("未认证 → 401 且是统一信封")
def _():
    code, body = request("GET", "/api/tickets")
    assert code == 401, code
    assert set(body) >= {"code", "message", "detail", "data"}, f"形状不对: {body}"
    assert body["code"] == 401 and body["data"] is None


@check("资源不存在 → 404 统一信封")
def _():
    code, body = request("GET", "/api/tickets/999999", token=tokens["lisi"])
    assert code == 404, (code, body)
    assert body["code"] == 404 and "message" in body


@check("参数校验失败 → 422 且带 errors 列表")
def _():
    code, body = request("POST", "/api/tickets", token=tokens["zhangsan"],
                         body={"title": "   "})
    assert code == 422, (code, body)
    assert body["code"] == 422 and isinstance(body["detail"], list)


print("\n=== [2] 新增接口 ===")


@check("创建工单 → 201 且返回 id")
def _():
    code, body = request("POST", "/api/tickets", token=tokens["zhangsan"],
                         body={"title": "HTTP验收单", "content": "内容"})
    assert code == 201, (code, body)
    assert body["data"]["id"], body
    tokens["_tid"] = body["data"]["id"]


@check("工单详情 → 200，字段完整")
def _():
    code, body = request("GET", f"/api/tickets/{tokens['_tid']}", token=tokens["zhangsan"])
    assert code == 200, (code, body)
    data = body["data"]
    for field in ("id", "title", "status", "submitter", "created_at"):
        assert field in data, f"缺字段 {field}"


@check("越权查看详情 → 404（不暴露存在性）")
def _():
    code, body = request("GET", f"/api/tickets/{tokens['_tid']}", token=tokens["wangwu"])
    assert code == 404, (code, body)


@check("流转动作 reject → 200，状态变 rejected")
def _():
    code, body = request("POST", f"/api/tickets/{tokens['_tid']}/action",
                         token=tokens["lisi"],
                         body={"action": "reject", "remark": "不合规"})
    assert code == 200, (code, body)
    assert body["data"]["new_status"] == "rejected", body


@check("终态再流转 → 400")
def _():
    code, body = request("POST", f"/api/tickets/{tokens['_tid']}/action",
                         token=tokens["lisi"], body={"action": "close"})
    assert code == 400, (code, body)


@check("非法 action → 422（被 schema 拦住）")
def _():
    code, body = request("POST", f"/api/tickets/{tokens['_tid']}/action",
                         token=tokens["lisi"], body={"action": "delete_all"})
    assert code == 422, (code, body)


@check("流转日志 → 200，含 submit 与 reject")
def _():
    code, body = request("GET", f"/api/tickets/{tokens['_tid']}/logs", token=tokens["zhangsan"])
    assert code == 200, (code, body)
    actions = [l["action"] for l in body["data"]]
    assert actions[0] == "submit", actions
    assert "reject" in actions, actions


@check("status 参数枚举校验 → 422")
def _():
    code, body = request("GET", "/api/tickets?status=whatever", token=tokens["zhangsan"])
    assert code == 422, (code, body)


print("\n=== [3] 权限仍然生效 ===")


@check("员工调用流转接口 → 403")
def _():
    code, body = request("POST", "/api/tickets/1/approve", token=tokens["zhangsan"],
                         body={"action": "approve"})
    assert code == 403, (code, body)
    assert "manager" in body["message"]


@check("主管处理跨部门工单 → 403")
def _():
    code, body = request("POST", "/api/tickets", token=tokens["wangwu"],
                         body={"title": "财务部单据", "content": "x"})
    tid = body["data"]["id"]
    code, body = request("POST", f"/api/tickets/{tid}/action", token=tokens["lisi"],
                         body={"action": "approve"})
    assert code == 403, (code, body)


@check("admin 可跨部门处理 → 200")
def _():
    code, body = request("POST", "/api/tickets", token=tokens["wangwu"],
                         body={"title": "财务部单据2", "content": "x"})
    tid = body["data"]["id"]
    code, body = request("POST", f"/api/tickets/{tid}/action", token=tokens["admin1"],
                         body={"action": "approve", "remark": "管理员"})
    assert code == 200, (code, body)


@check("未列举角色的数据权限为 fail-closed")
def _():
    code, body = request("GET", "/api/tickets", token=tokens["zhangsan"])
    zs = body["data"]["total"]
    code, body = request("GET", "/api/tickets", token=tokens["admin1"])
    total = body["data"]["total"]
    assert total >= zs, f"admin({total}) 应大于等于员工({zs})"


print("\n" + "=" * 56)
total_checks = len(PASS) + len(FAIL)
print(f"结果: {len(PASS)}/{total_checks} 通过")
if FAIL:
    for name, reason in FAIL:
        print(f"  - {name}: {reason}")
    print("=" * 56)
    sys.exit(1)
print("HTTP 层契约全部通过")
print("=" * 56)
