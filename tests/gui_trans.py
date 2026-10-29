"""验证色键透明改造：小卡片、设置页、完整模式、拖动残影。

跑法：python tests/gui_trans.py
产物：tests/tr_*.png（人工看，不进断言）
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-trans-")

import webview  # noqa: E402
from PIL import ImageGrab  # noqa: E402

import app as appmod  # noqa: E402

user32 = ctypes.windll.user32


def grab(hwnd: int, name: str, pad: int = 26) -> None:
    r = wt.RECT()
    user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    box = (max(0, r.left - pad), max(0, r.top - pad),
           min(1920, r.right + pad), min(1080, r.bottom + pad))
    ImageGrab.grab(bbox=box).save(ROOT / "tests" / name)
    print("shot", name, box, flush=True)


def main() -> None:
    state = appmod.load_state()
    state.update({
        "mode": "mini", "auto_collapse": False, "collapse_min": False,
        "snap": False, "on_top": True, "close_action": "quit",
    })
    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "tr", url=str(ROOT / "ui" / "index.html"), js_api=api,
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
            win.move(500, 200)
            time.sleep(1.0)
            grab(hwnd, "tr_mini.png")

            # 设置页（有 backdrop-filter，透明窗口下最容易翻车的地方）
            win.evaluate_js("document.getElementById('btnSettingsMini').click()")
            time.sleep(1.0)
            grab(hwnd, "tr_settings.png")

            win.evaluate_js("document.getElementById('setBack').click()")
            time.sleep(0.6)

            # 完整模式
            win.evaluate_js("document.getElementById('btnMode').click()")
            time.sleep(1.4)
            grab(hwnd, "tr_full.png", pad=14)

            # 拖一段距离，看旧位置有没有残影
            win.move(700, 260)
            time.sleep(0.8)
            grab(hwnd, "tr_drag.png", pad=60)

            # 切回小卡片
            win.evaluate_js("document.getElementById('btnMode').click()")
            time.sleep(1.2)
            grab(hwnd, "tr_back_mini.png")
            print("done", flush=True)
        except Exception as exc:
            print("runner error", repr(exc), flush=True)
        finally:
            try:
                window.destroy()
            except Exception:
                pass

    import threading

    threading.Thread(target=runner, daemon=True).start()
    webview.start(debug=False)


if __name__ == "__main__":
    main()
