"""文件对话框可用性：导出/导入会走 WinForms 的模态对话框。

js_api 回调跑在非 UI 线程，对话框却是 UI 线程的资源。这里验证：
  · 对话框能不能真的弹出来（找到 #32770 窗口）；
  · 弹出期间 UI 线程是否还活着；
  · 关掉之后调用能不能正常返回，而不是把整个应用卡死。

注意：pywebview 的 api 调用在 JS 里返回 Promise，evaluate_js 不会等它，
所以结果要回填到 window.__r 再轮询。

用法：venv/Scripts/python.exe tests/gui_dialog.py
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-dlg-")

import webview  # noqa: E402

import app as appmod  # noqa: E402

u32 = ctypes.WinDLL("user32", use_last_error=True)
WM_CLOSE = 0x0010


def find_dialog() -> list:
    hits = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not u32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "#32770":
            return True
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(hwnd, buf, 256)
        hits.append([hwnd, buf.value])
        return True

    u32.EnumWindows(cb, 0)
    return hits


def main() -> None:
    state = appmod.load_state()
    state["snap"] = False
    state["auto_collapse"] = False
    state["collapse_min"] = False

    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "dlg", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window
    result: dict = {"export": None, "import": None, "alive": None, "dialogs": []}
    DATA = Path(tempfile.gettempdir()) / "xixi-dlg-backup.json"

    def wait_dialog_and_close(timeout: float = 8.0) -> bool:
        """等对话框出现，记录标题并关掉（等于用户点取消）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            hits = find_dialog()
            if hits:
                result["dialogs"].append(hits)
                time.sleep(0.4)
                for hwnd, _title in hits:
                    u32.PostMessageW(ctypes.c_void_p(hwnd), WM_CLOSE, None, None)
                return True
            time.sleep(0.15)
        return False

    def call_async(js_expr: str, key: str, seconds: float = 6.0) -> None:
        window.evaluate_js(
            "window.__r='pending';"
            + js_expr
            + ".then(function(v){window.__r=JSON.stringify({ok:true,v:String(v).slice(0,120)});})"
            ".catch(function(e){window.__r=JSON.stringify({ok:false,e:String(e).slice(0,120)});});"
        )
        t0 = time.time()
        while time.time() - t0 < seconds:
            v = window.evaluate_js("window.__r")
            if v and v != "pending":
                result[key] = {"js": v, "ms": int((time.time() - t0) * 1000)}
                return
            time.sleep(0.2)
        result[key] = {"js": "TIMEOUT", "ms": int((time.time() - t0) * 1000)}

    def runner() -> None:
        time.sleep(2.8)
        # 导出：先起监听线程，再从前端发起（走真实的 js_api 线程）
        th = threading.Thread(target=wait_dialog_and_close, daemon=True)
        th.start()
        call_async(
            "window.pywebview.api.export_backup('{\"version\":3,\"todos\":[]}')",
            "export", seconds=10,
        )
        try:
            result["alive"] = {"value": window.evaluate_js("1+1")}
        except Exception as exc:
            result["alive"] = {"error": str(exc)[:200]}

        th2 = threading.Thread(target=wait_dialog_and_close, daemon=True)
        th2.start()
        call_async("window.pywebview.api.import_backup()", "import", seconds=10)

        log = Path(os.environ["XIXI_TODO_DATA_DIR"]) / "app.log"
        result["log"] = log.read_text(encoding="utf-8")[-1500:] if log.exists() else ""

        out = Path(__file__).resolve().parent / "gui_dialog_result.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.stdout.flush()
        os._exit(0)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
