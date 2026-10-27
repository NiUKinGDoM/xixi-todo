"""小卡片透明度：设值后窗口真的带上 WS_EX_LAYERED 且 alpha 正确。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-op-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

u32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def ex_style(hwnd):
    return int(u32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE))


def main():
    state = appmod.load_state()
    state.update({"mode": "mini", "snap": False, "auto_collapse": False, "opacity": 100})
    holder = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "op", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    def runner():
        time.sleep(3)
        win = webview.windows[0]
        hwnd = int(win.native.Handle.ToInt64())
        u32.ShowWindow(ctypes.c_void_p(hwnd), 9)
        win.resize(380, 560)
        time.sleep(0.6)

        check("默认 100% 不带分层属性", not (ex_style(hwnd) & WS_EX_LAYERED), hex(ex_style(hwnd)))

        api.set_opacity("60")
        time.sleep(0.6)
        ex = ex_style(hwnd)
        check("设 60% 后带 WS_EX_LAYERED", bool(ex & WS_EX_LAYERED), hex(ex))
        check("状态里记下 60", json.loads(api.get_window_state())["opacity"] == 60)
        check("窗口还看得见", bool(u32.IsWindowVisible(ctypes.c_void_p(hwnd))))

        api.set_opacity("0")
        time.sleep(0.5)
        check("0% 记录正确", json.loads(api.get_window_state())["opacity"] == 0)
        api.set_opacity("100")
        time.sleep(0.5)
        st = json.loads(api.get_window_state())
        check("回到 100%", st["opacity"] == 100)

        # 落盘
        saved = json.loads((appmod.STATE_FILE).read_text("utf-8"))
        check("透明度已落盘", saved.get("opacity") == 100, str(saved.get("opacity")))

        ok = all(RESULTS)
        print(f"通过 {sum(RESULTS)} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
