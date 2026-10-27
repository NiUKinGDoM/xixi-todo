"""空闲自动收起：小卡片放着一会儿不动，自己缩成三个点。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-idle-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def main():
    state = appmod.load_state()
    state.update({"mode": "mini", "snap": True, "auto_collapse": False, "collapse_min": True})
    holder = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "idle", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    def runner():
        time.sleep(3)
        win = webview.windows[0]
        win.move(700, 350)
        time.sleep(1)
        check("初始未收起", json.loads(api.get_window_state())["collapsed"] is False)

        # 什么都不做，等它自己收
        deadline = time.time() + 22
        collapsed = False
        while time.time() < deadline:
            if json.loads(api.get_window_state())["collapsed"]:
                collapsed = True
                break
            time.sleep(0.8)
        st = json.loads(api.get_window_state())
        cls = win.evaluate_js("document.body.className")
        dbg = win.evaluate_js(
            "JSON.stringify({body:document.body.className,"
            "settingsHidden:document.getElementById('settingsPanel').hidden,"
            "modalHidden:document.getElementById('modalMask').hidden,"
            "updHidden:document.getElementById('updMask').hidden,"
            "adding:document.body.classList.contains('is-adding')})"
        )
        print("调试:", dbg, flush=True)
        check("闲置后自动收起", collapsed, str(st)[:80])
        check("页面切到小条形态", "is-collapsed" in cls, cls)

        # 收起来后点一下能展开
        user32 = __import__("ctypes").windll.user32
        hwnd = int(win.native.Handle.ToInt64())
        class _R:
            pass
        import ctypes, ctypes.wintypes as wt
        r = wt.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
        user32.SetCursorPos(cx, cy)
        time.sleep(0.1)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.1)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(1.6)
        st2 = json.loads(api.get_window_state())
        check("点一下能展开", st2["collapsed"] is False, str(st2)[:70])

        ok = all(RESULTS)
        print(f"通过 {sum(RESULTS)} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
