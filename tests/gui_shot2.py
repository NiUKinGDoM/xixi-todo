"""本次改动的视觉验收：已完成横线、置顶不计入进度、透明卡片。

跑法：python tests/gui_shot2.py
"""
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-shot2-")

import webview  # noqa: E402
from PIL import ImageGrab  # noqa: E402

import app as appmod  # noqa: E402

user32 = ctypes.windll.user32


def grab(hwnd: int, name: str, pad: int = 24) -> None:
    r = wt.RECT()
    user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    box = (max(0, r.left - pad), max(0, r.top - pad), r.right + pad, r.bottom + pad)
    ImageGrab.grab(bbox=box).save(ROOT / "tests" / name)
    print("shot", name, flush=True)


def main() -> None:
    state = appmod.load_state()
    state.update({
        "mode": "mini", "auto_collapse": False, "collapse_min": False,
        "snap": False, "on_top": True, "close_action": "quit",
    })
    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "shot2", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=True, shadow=False, on_top=True,
    )
    holder["window"] = window
    window.events.shown += lambda: appmod.enable_colorkey(window)

    def runner() -> None:
        try:
            time.sleep(3.5)
            win = webview.windows[0]
            hwnd = int(win.native.Handle.ToInt64())
            win.resize(380, 560)
            win.move(560, 220)
            time.sleep(0.8)

            add = (
                "(function(){var i=document.getElementById('inputText');"
                "i.value=%s;document.getElementById('addBtn').click();})()"
            )
            for title in ["买牛奶", "写周报", "给客户回电话", "整理报价单"]:
                win.evaluate_js(add % json.dumps(title))
                time.sleep(0.15)

            # 第一条标记完成，第二条置顶
            win.evaluate_js("document.querySelectorAll('.todo-item .check')[0].click()")
            time.sleep(0.35)
            win.evaluate_js("document.querySelectorAll('.todo-item .pin-btn')[1].click()")
            time.sleep(0.6)

            print("进度:", win.evaluate_js(
                "document.getElementById('progressPct').textContent + ' | ' + "
                "document.getElementById('progressNote').textContent + ' | mini=' + "
                "document.getElementById('miniStat').textContent"), flush=True)
            grab(hwnd, "t2_mini_done.png")

            # 完整模式看横线
            win.evaluate_js("document.getElementById('btnMode').click()")
            time.sleep(1.4)
            grab(hwnd, "t2_full_done.png", pad=12)
            time.sleep(1.2)
            grab(hwnd, "t2_full_done2.png", pad=12)
            print("done", flush=True)
        except Exception as exc:
            print("runner error", repr(exc), flush=True)
        finally:
            try:
                window.destroy()
            except Exception:
                pass

    threading.Thread(target=runner, daemon=True).start()
    webview.start(debug=False)


if __name__ == "__main__":
    main()
