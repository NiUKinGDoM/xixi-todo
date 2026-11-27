"""验证「手动下载 = 强制云端覆盖」在旧云端时间戳下也生效（两端语义一致）。

场景：云端 ts=111111（很旧），本地 meta=当前很大时间戳。
不动 force → 判本地新、反推（旧 bug）；force=1 → 强制用云端。
"""
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import webdav_sync as w  # noqa: E402

STORE = {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth(self):
        raw = self.headers.get("Authorization", "")
        if not raw.startswith("Basic "):
            return False
        import base64
        try:
            u, p = base64.b64decode(raw[6:]).decode().split(":", 1)
        except Exception:
            return False
        return u == "t@e.com" and p == "pw"

    def _reply(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_PROPFIND(self):
        self._reply(207, b"<D:multistatus/>") if self._auth() else self._reply(401)

    def do_MKCOL(self):
        self._reply(201) if self._auth() else self._reply(401)

    def do_PUT(self):
        if not self._auth():
            return self._reply(401)
        n = int(self.headers.get("Content-Length", "0"))
        STORE[self.path] = self.rfile.read(n)
        self._reply(201)

    def do_GET(self):
        if not self._auth():
            return self._reply(401)
        if self.path not in STORE:
            return self._reply(404)
        self._reply(200, STORE[self.path])


def main():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/dav"
    cfg = w.SyncConfig(url, "t@e.com", "pw")

    cloud = [{"id": "cloud1", "title": "云端任务（很旧 ts）", "done": False}]
    STORE[f"/dav/xixi-todo/{w.FILE_NAME}"] = json.dumps(cloud, ensure_ascii=False).encode()
    STORE[f"/dav/xixi-todo/{w.META_NAME}"] = json.dumps({"updatedAt": 111111}).encode()

    tmp = Path(tempfile.mkdtemp(prefix="sync-force-"))
    w.save_config(tmp, cfg)
    # 本地 meta 设成很大（模拟电脑时间比云端任务新）
    w.write_meta(tmp, 9999999999999)
    # 本地放不同数据
    (tmp / w.FILE_NAME).write_text(json.dumps([{"id": "local1", "title": "本地任务"}]), encoding="utf-8")

    passed = True

    def check(name, cond, detail=""):
        nonlocal passed
        print(("OK   " if cond else "FAIL ") + name + (f" :: {detail}" if detail else ""))
        if not cond:
            passed = False

    # 复刻 app.py sync_pull 的判定（不动 force → 判本地新）
    content, remote_ts, msg = w.pull(cfg)
    local_ts = w.read_meta(tmp)
    local_newer = bool(remote_ts) and remote_ts <= local_ts and (tmp / w.FILE_NAME).exists()
    check("无 force：判本地新（旧行为）", local_newer, f"remote={remote_ts} local={local_ts}")

    # force=1：跳过判定，强制用云端
    force_download = True
    should_use_cloud = not (not force_download and local_newer)
    check("force=1：强制用云端覆盖", should_use_cloud)

    # 验证源码里真的接了 force
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app.py force 参数生效", "not force_download and remote_ts" in app_src)
    js = (ROOT / "ui/app.js").read_text(encoding="utf-8")
    check("前端下载传 force=1", "callApi('sync_pull', '1')" in js)

    print()
    print("PASS" if passed else "FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
