import urllib.request
import json

url = "https://httpbin.org/get?status=pending&page=1"
with urllib.request.urlopen(url) as resp:
    print("状态码：", resp.status)          # ← 看看是不是 200
    print("响应头：", resp.headers["Content-Type"])
    body = resp.read().decode("utf-8")
    print("响应体：", body[:300])

req = urllib.request.Request(
    "https://httpbin.org/post",
    data=json.dumps({"title": "电脑坏了"}, ensure_ascii= False ).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    print("\nPOST 状态码：", resp.status)
    print("POST 响应体：", resp.read().decode("utf-8")[:400])