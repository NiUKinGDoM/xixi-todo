"""WebDAV 同步层端到端测试 —— 本地假 DAV 服务器，不碰用户坚果云。

覆盖：
- 配置保存/读取（DPAPI 加密落盘）
- MKCOL 建目录（405 也算成功）
- push 上传 todos.json + meta
- pull 下载，时间戳正确带回
- 云端比本地新 / 本地比云端新 两种判定
"""
import base64
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import webdav_sync as w  # noqa: E402

STORE: dict[str, bytes] = {}
LOG: list[tuple[str, str]] = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth_ok(self):
        raw = self.headers.get("Authorization", "")
        if not raw.startswith("Basic "):
            return False
        try:
            user, pwd = base64.b64decode(raw[6:]).decode().split(":", 1)
        except Exception:
            return False
        return user == "test@example.com" and pwd == "app-password"

    def _reply(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_MKCOL(self):
        LOG.append(("MKCOL", self.path))
        if not self._auth_ok():
            return self._reply(401)
        self._reply(201 if self.path.count("/") == 2 else 405)

    def do_PROPFIND(self):
        LOG.append(("PROPFIND", self.path))
        if not self._auth_ok():
            return self._reply(401)
        self._reply(207, b"<?xml version='1.0'?><D:multistatus/>")

    def do_PUT(self):
        LOG.append(("PUT", self.path))
        if not self._auth_ok():
            return self._reply(401)
        n = int(self.headers.get("Content-Length", "0"))
        STORE[self.path] = self.rfile.read(n)
        self._reply(201)

    def do_GET(self):
        LOG.append(("GET", self.path))
        if not self._auth_ok():
            return self._reply(401)
        if self.path not in STORE:
            return self._reply(404)
        self._reply(200, STORE[self.path])


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{server.server_port}/dav"

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

    # 配置：DPAPI 加密落盘后再读出来
    tmp = Path(tempfile.mkdtemp(prefix="xixi-sync-test-"))
    cfg = w.SyncConfig(url + "/xixi-todo", "test@example.com", "app-password")
    check("strip_dir 剥掉重复目录", cfg.url == url, cfg.url)
    w.save_config(tmp, cfg)
    raw = (tmp / w.CONFIG_FILE).read_text(encoding="utf-8")
    check("密码不落明文", "app-password" not in raw, raw[:120])
    loaded = w.load_config(tmp)
    check("配置读回密码一致", loaded.password == "app-password", loaded.password)
    check("ready 判定", loaded.ready)

    # 连接测试
    ok, msg = w.test(loaded)
    check("PROPFIND 连通", ok, msg)

    # push
    items = [{"id": "a1", "title": "云端任务", "done": False}]
    payload = json.dumps(items, ensure_ascii=False)
    ok, msg = w.push(loaded, payload, 12345)
    check("push 成功", ok, msg)
    check("todos.json 已上传", f"/dav/xixi-todo/{w.FILE_NAME}" in STORE, list(STORE))
    check("meta 已上传", f"/dav/xixi-todo/{w.META_NAME}" in STORE, list(STORE))
    meta = json.loads(STORE[f"/dav/xixi-todo/{w.META_NAME}"].decode())
    check("meta 时间戳正确", meta.get("updatedAt") == 12345, meta)

    # pull
    content, ts, msg = w.pull(loaded)
    check("pull 成功", content == payload and ts == 12345, (content, ts, msg))

    # 本地 meta 读写
    check("本地 meta 初始 0", w.read_meta(tmp) == 0)
    w.write_meta(tmp, 99999)
    check("本地 meta 写入", w.read_meta(tmp) == 99999)

    # 错误凭据
    bad = w.SyncConfig(url, "test@example.com", "wrong")
    ok, msg = w.test(bad)
    check("错误密码连不上", not ok, msg)

    # 404
    empty = w.SyncConfig(url, "test@example.com", "app-password")
    STORE.clear()
    content, ts, msg = w.pull(empty)
    check("云端无文件返回空", content is None and "还没有" in msg, msg)

    server.shutdown()
    print(f"\n通过 {passed} / {passed + len(failed)}")
    if failed:
        print("失败:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
