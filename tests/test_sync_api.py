"""Api 层同步行为测试 —— 假 DAV + 真 Api，不碰用户数据。

覆盖本轮修的每一条：
- 配置「先落盘再测试」：网络不通也能保存配置
- 密码留空 = 沿用已保存的
- 同步状态：push/pull 成功失败都要有状态，不能只写日志
- 覆盖前备份：云端比本地新时，本地旧数据要留副本
- pull 后 count/changed 正确，前端据此刷新界面
- flush_sync：关窗前把防抖中的推送做完
- 本地比云端新：反推上去，不覆盖本地
"""
import base64
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
import webdav_sync as w  # noqa: E402

STORE: dict[str, bytes] = {}
FAIL_NEXT = {"on": False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth_ok(self):
        raw = self.headers.get("Authorization", "")
        if not raw.startswith("Basic "):
            return False
        try:
            u, p = base64.b64decode(raw[6:]).decode().split(":", 1)
        except Exception:
            return False
        return u == "test@example.com" and p == "app-password"

    def _reply(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_MKCOL(self):
        self._reply(201 if self.path.count("/") == 2 else 405)

    def do_PROPFIND(self):
        if FAIL_NEXT["on"]:
            FAIL_NEXT["on"] = False
            return self._reply(500)
        if not self._auth_ok():
            return self._reply(401)
        self._reply(207, b"<D:multistatus/>")

    def do_PUT(self):
        if not self._auth_ok():
            return self._reply(401)
        n = int(self.headers.get("Content-Length", "0"))
        STORE[self.path] = self.rfile.read(n)
        self._reply(201)

    def do_GET(self):
        if not self._auth_ok():
            return self._reply(401)
        if self.path not in STORE:
            return self._reply(404)
        self._reply(200, STORE[self.path])


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/dav"

    tmp = Path(tempfile.mkdtemp(prefix="xixi-sync-api-test-"))
    store = appmod.Store(tmp / "todos.json")
    api = appmod.Api(store, {"window": None}, {})

    passed = 0
    failed = []

    def check(name, cond, detail=""):
        nonlocal passed
        if cond:
            passed += 1
            print(f"OK   {name}")
        else:
            failed.append(name)
            print(f"FAIL {name} :: {detail}")

    def j(raw):
        try:
            return json.loads(raw or "{}")
        except Exception:
            return {}

    # 1. 网络不通也要保存配置
    FAIL_NEXT["on"] = True
    payload = json.dumps({"url": url, "user": "test@example.com", "password": "app-password"})
    r = j(api.set_sync_config(payload))
    check("连接失败时配置仍保存", not r.get("ok") and api._sync_cfg.ready, r)
    check("失败时密码已落盘", w.load_config(tmp).password == "app-password")

    # 2. 密码留空沿用已保存的
    payload2 = json.dumps({"url": url, "user": "test@example.com", "password": ""})
    j(api.set_sync_config(payload2))
    check("密码留空沿用旧密码", api._sync_cfg.password == "app-password", api._sync_cfg.password)
    check("保存后状态有记录", j(api.get_sync_state()).get("at", 0) > 0)

    # 3. push 成功 → 状态 ok + 本地时间戳更新
    store.save([{"id": "a", "title": "本地任务", "done": False}])
    ok, msg = api._do_push()
    st = j(api.get_sync_state())
    check("push 成功", ok, msg)
    check("push 状态 ok", st.get("state") == "ok", st)
    check("push 后本地时间戳更新", w.read_meta(tmp) > 0, w.read_meta(tmp))
    check("云端有数据", f"/dav/xixi-todo/{w.FILE_NAME}" in STORE, list(STORE))

    # 4. 云端更新 → pull 覆盖本地 + 留备份
    remote_items = [{"id": "b", "title": "云端任务", "done": False}]
    cloud_ts = w.read_meta(tmp) + 100000
    STORE[f"/dav/xixi-todo/{w.FILE_NAME}"] = json.dumps(remote_items, ensure_ascii=False).encode()
    STORE[f"/dav/xixi-todo/{w.META_NAME}"] = json.dumps(
        {"updatedAt": cloud_ts, "device": "android"}).encode()
    r = j(api.sync_pull())
    check("pull 覆盖本地", r.get("changed") and r.get("count") == 1, r)
    check("pull 带回云端数据", store.load()[0]["title"] == "云端任务", store.load())
    check("覆盖前留备份", bool(r.get("backup")) and Path(r["backup"]).exists(), r.get("backup"))
    check("pull 后时间戳跟着云端", w.read_meta(tmp) == cloud_ts, w.read_meta(tmp))

    # 5. 本地更新 → 反推云端，不覆盖本地
    store.save([{"id": "c", "title": "本地更新版", "done": False}])
    local_ts = w.read_meta(tmp) + 100000
    w.write_meta(tmp, local_ts)
    r = j(api.sync_pull())
    check("本地新时不覆盖", not r.get("changed"), r)
    check("本地新时反推云端", "已推到云端" in r.get("msg", ""), r.get("msg"))
    check("本地数据还在", store.load()[0]["title"] == "本地更新版", store.load())

    # 6. flush_sync 把防抖中的 push 做完
    store.save([{"id": "d", "title": "关窗前最后一条", "done": False}])
    api._schedule_push()
    check("防抖定时器已设", api._push_timer is not None)
    api.flush_sync(wait=3)
    pushed = json.loads(STORE[f"/dav/xixi-todo/{w.FILE_NAME}"].decode())
    check("flush 后最后一条已上云", pushed[0]["title"] == "关窗前最后一条", pushed)

    # 7. push 失败要有 error 状态（用错误密码）
    bad = w.SyncConfig(url, "test@example.com", "wrong")
    api._sync_cfg = bad
    ok, msg = api._do_push()
    st = j(api.get_sync_state())
    check("错误凭据 push 失败", not ok, msg)
    check("失败状态可见", st.get("state") == "error" and bool(st.get("msg")), st)

    server.shutdown()
    print(f"\n通过 {passed} / {passed + len(failed)}")
    if failed:
        print("失败:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
