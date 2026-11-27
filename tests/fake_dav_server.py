"""常驻假 WebDAV 服务器（排查两端同步用）。监听 0.0.0.0:8899，模拟器用 10.0.2.2:8899 访问。
记录所有请求到 LOG.txt，方便对比桌面/手机的请求差异。
"""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORE_FILE = ROOT / "fake_dav_store.json"
LOG_FILE = ROOT / "fake_dav_log.txt"

STORE = {}
if STORE_FILE.exists():
    try:
        STORE = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        STORE = {}


def save_store():
    STORE_FILE.write_text(json.dumps(STORE, ensure_ascii=False, indent=2), encoding="utf-8")


def log(line):
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth(self):
        raw = self.headers.get("Authorization", "")
        if not raw.startswith("Basic "):
            return False
        try:
            u, p = base64.b64decode(raw[6:]).decode("utf-8").split(":", 1)
        except Exception:
            return False
        return u == "test@example.com" and p == "app-password"

    def _reply(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _record(self, method):
        log(f"{method} {self.path} | auth={self.headers.get('Authorization','<none>')[:30]} | ct={self.headers.get('Content-Type','-')}")

    def do_PROPFIND(self):
        self._record("PROPFIND")
        if not self._auth():
            return self._reply(401)
        self._reply(207, b"<?xml version='1.0'?><D:multistatus/>")

    def do_MKCOL(self):
        self._record("MKCOL")
        if not self._auth():
            return self._reply(401)
        self._reply(201 if self.path.count("/") == 2 else 405)

    def do_PUT(self):
        self._record("PUT")
        if not self._auth():
            return self._reply(401)
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n)
        log(f"  BODY: {body.decode('utf-8', 'replace')[:300]}")
        STORE[self.path] = body.decode("utf-8")
        save_store()
        self._reply(201)

    def do_GET(self):
        self._record("GET")
        if not self._auth():
            return self._reply(401)
        if self.path not in STORE:
            return self._reply(404)
        self._reply(200, STORE[self.path].encode("utf-8"))


if __name__ == "__main__":
    LOG_FILE.write_text("=== fake DAV started ===\n", encoding="utf-8")
    server = ThreadingHTTPServer(("0.0.0.0", 8899), Handler)
    print("listening on 0.0.0.0:8899", flush=True)
    server.serve_forever()
