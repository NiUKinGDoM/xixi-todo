"""坚果云 / 标准 WebDAV 同步层 —— 与手机端 todo-android/TodoSync.kt 对齐。

设计要点：
- 云端路径固定 ``<url>/xixi-todo/todos.json``，手机端同名，两端直接互通。
- 另存 ``todos.meta.json``（{"updatedAt": 毫秒时间戳}）判断谁更新，
  避免「手机改了、电脑也改了，一同步就互相覆盖」。
- 配置存在 ``sync.json``；密码用 Windows DPAPI（CryptProtectData）加密，
  密钥跟随当前 Windows 用户，别人拷走文件也解不开。
- 只用标准库：urllib + ctypes，不新增依赖。
"""

from __future__ import annotations

import base64
import ctypes
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from pathlib import Path
from typing import Any

DIR_NAME = "xixi-todo"
FILE_NAME = "todos.json"
META_NAME = "todos.meta.json"
CONFIG_FILE = "sync.json"

# ---------- DPAPI：Windows 自带的凭据加密 ----------

class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _dpapi(plain: bytes, encrypt: bool) -> bytes:
    """调 crypt32 的 CryptProtectData / CryptUnprotectData，失败时抛异常。"""
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    src = (ctypes.c_byte * len(plain)).from_buffer_copy(plain)
    blob_in = _DataBlob(len(plain), src)
    blob_out = _DataBlob(0, ctypes.POINTER(ctypes.c_byte)())

    fn = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    fn.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    fn.restype = wintypes.BOOL
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise OSError(f"DPAPI failed: {ctypes.get_last_error()}")

    try:
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        return bytes(data)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, wintypes.HANDLE))


def seal(plain: str) -> str:
    """加密成 dpapi:base64；失败时留明文标记 xk0:，让诊断能发现。"""
    if not plain:
        return ""
    try:
        return "dpapi:" + base64.b64encode(_dpapi(plain.encode("utf-8"), True)).decode("ascii")
    except Exception:
        return "xk0:" + plain


def unseal(stored: str) -> str:
    if not stored:
        return ""
    if stored.startswith("xk0:"):
        return stored[4:]
    if not stored.startswith("dpapi:"):
        return stored  # 老版本明文，兼容读
    try:
        return _dpapi(base64.b64decode(stored[6:]), False).decode("utf-8")
    except Exception:
        return ""


# ---------- 配置 ----------

def strip_dir(raw: str) -> str:
    """用户可能填了带 /xixi-todo 的地址，剥掉，只拼一次。"""
    b = (raw or "").strip().rstrip("/")
    suffix = "/" + DIR_NAME
    while b.endswith(suffix):
        b = b[: -len(suffix)].rstrip("/")
    return b


class SyncConfig:
    def __init__(self, url: str = "", user: str = "", password: str = ""):
        self.url = strip_dir(url)
        self.user = (user or "").strip()
        self.password = password or ""

    @property
    def ready(self) -> bool:
        return bool(self.url and self.user and self.password)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "user": self.user,
            "password": seal(self.password),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SyncConfig":
        return cls(
            url=str(d.get("url", "")),
            user=str(d.get("user", "")),
            password=unseal(str(d.get("password", ""))),
        )


def load_config(data_dir: Path) -> SyncConfig:
    path = data_dir / CONFIG_FILE
    if not path.exists():
        return SyncConfig()
    try:
        return SyncConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return SyncConfig()


def save_config(data_dir: Path, cfg: SyncConfig) -> None:
    target = data_dir / CONFIG_FILE
    tmp = target.with_name(f"{CONFIG_FILE}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


# ---------- WebDAV ----------

class SyncError(Exception):
    pass


def _request(cfg: SyncConfig, method: str, url: str, body: bytes | None = None,
             headers: dict[str, str] | None = None, timeout: int = 20):
    h = {
        "Authorization": "Basic " + base64.b64encode(
            f"{cfg.user}:{cfg.password}".encode("utf-8")
        ).decode("ascii"),
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    # http:// 是本地/测试服务器，不能传 ssl context（urllib 会拒绝）
    if url.lower().startswith("https://"):
        ctx = ssl._create_unverified_context()  # 国内代理证书链常不全，与更新下载保持一致
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return urllib.request.urlopen(req, timeout=timeout)


def _file_url(cfg: SyncConfig, name: str) -> str:
    return f"{cfg.url}/{DIR_NAME}/{urllib.parse.quote(name)}"


def test(cfg: SyncConfig) -> tuple[bool, str]:
    if not cfg.url or not cfg.user:
        return False, "请先填写地址和账号"
    if not cfg.password:
        return False, "还缺应用密码"
    # 根路径用带斜杠的形式：坚果云对 /dav 会 301 到 /dav/，直接请求 /dav/ 就不会重定向。
    # 这样测试连接不会假报 HTTP 301（push/pull 走的是具体文件路径，本来就不受影响）。
    root_url = cfg.url.rstrip("/") + "/"
    try:
        with _request(cfg, "PROPFIND", root_url, b"", {"Depth": "0"}) as r:
            return (True, "连接正常") if 200 <= r.status < 300 else (False, f"HTTP {r.status}")
    except urllib.error.HTTPError as e:
        # 405 = 节点不支持 PROPFIND 根；301/302 = 服务端重定向（凭据已通过校验）
        # 都算「连得上」，不能报成同步失败。
        return (True, "连接正常") if e.code in (405, 301, 302) else (False, f"HTTP {e.code}")
    except Exception as e:
        return False, str(e) or "网络错误"


def _ensure_dir(cfg: SyncConfig) -> bool:
    try:
        with _request(cfg, "MKCOL", f"{cfg.url}/{DIR_NAME}", b"") as r:
            return True
    except urllib.error.HTTPError as e:
        return e.code in (405, 301, 302)
    except Exception:
        return False


def push(cfg: SyncConfig, content: str, updated_at_ms: int) -> tuple[bool, str]:
    """上传 todos.json + meta。meta 失败不否定主数据成功。"""
    if not cfg.ready:
        return False, "同步配置不完整"
    if not _ensure_dir(cfg):
        return False, f"建不了目录 {DIR_NAME}"
    try:
        body = content.encode("utf-8")
        with _request(cfg, "PUT", _file_url(cfg, FILE_NAME), body,
                      {"Content-Type": "application/json; charset=utf-8"}):
            pass
        meta = json.dumps(
            {"updatedAt": int(updated_at_ms), "device": "windows"}, ensure_ascii=False
        ).encode("utf-8")
        try:
            with _request(cfg, "PUT", _file_url(cfg, META_NAME), meta,
                          {"Content-Type": "application/json; charset=utf-8"}):
                pass
        except Exception:
            pass  # 老客户端不读 meta，写不进去也不影响它用 todos.json
        return True, "已上传"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e) or "网络错误"


def pull(cfg: SyncConfig) -> tuple[str | None, int, str]:
    """返回 (内容, 云端时间戳, 提示)。云端没 meta 时时间戳为 0。"""
    if not cfg.ready:
        return None, 0, "同步配置不完整"
    try:
        with _request(cfg, "GET", _file_url(cfg, FILE_NAME)) as r:
            content = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, 0, "云端还没有待办文件"
        return None, 0, f"HTTP {e.code}"
    except Exception as e:
        return None, 0, str(e) or "网络错误"

    ts = 0
    try:
        with _request(cfg, "GET", _file_url(cfg, META_NAME)) as r:
            meta = json.loads(r.read().decode("utf-8"))
            ts = int(meta.get("updatedAt", 0))
    except Exception:
        pass
    return content, ts, "已下载"


def read_meta(data_dir: Path) -> int:
    path = data_dir / META_NAME
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("updatedAt", 0))
    except Exception:
        return 0


def write_meta(data_dir: Path, updated_at_ms: int) -> None:
    path = data_dir / META_NAME
    tmp = path.with_name(f"{META_NAME}.{time.time_ns()}.tmp")
    tmp.write_text(
        json.dumps({"updatedAt": int(updated_at_ms), "device": "windows"}, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)
