"""自动收起全链路验证：拖到边缘 → 吸附 → 收成小条 → 页面切到小条形态。

重点验证用户报的两件事：
1. 拖到边上到底收不收得进去
2. 收进去之后，页面有没有真的变成「三个点」的小条，
   而不是把整块界面硬塞进 104x20 的窗口
"""

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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-col-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

user32 = ctypes.windll.user32
LEFTDOWN, LEFTUP = 0x0002, 0x0004
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def client_xy(hwnd, cx, cy):
    p = wt.POINT(int(cx), int(cy))
    user32.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(p))
    return p.x, p.y


def drag(x1, y1, x2, y2, steps=14):
    user32.SetCursorPos(x1, y1)
    time.sleep(0.12)
    user32.mouse_event(LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.15)
    for i in range(1, steps + 1):
        user32.SetCursorPos(int(x1 + (x2 - x1) * i / steps),
                            int(y1 + (y2 - y1) * i / steps))
        time.sleep(0.035)
    time.sleep(0.2)
    user32.mouse_event(LEFTUP, 0, 0, 0, 0)
    time.sleep(1.4)


def main() -> None:
    state = appmod.load_state()
    state.update({
        "mode": "mini", "snap": True, "auto_collapse": True,
        "collapse_min": False, "on_top": True,
    })
    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    appmod.Store(appmod.DATA_FILE).save([
        {"id": "a", "title": "验证自动收起", "priority": "medium", "due": "",
         "time": "", "repeat": "none", "note": "", "done": False, "createdAt": 1},
    ])
    window = webview.create_window(
        "collapse", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    def runner() -> None:
        time.sleep(3)
        win = webview.windows[0]
        hwnd = int(win.native.Handle.ToInt64())
        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)
        win.resize(380, 560)
        time.sleep(0.5)
        win.move(600, 400)
        time.sleep(0.6)

        x0, y0, w, h = rect(hwnd)
        print(f"起点 {x0},{y0} {w}x{h}", flush=True)

        # 抓标题栏拖到屏幕顶边
        sx, sy = client_xy(hwnd, 90, 16)
        drag(sx, sy, sx, 2)

        time.sleep(1.2)
        st = json.loads(api.get_window_state())
        x1, y1, w1, h1 = rect(hwnd)
        body = win.evaluate_js(
            "JSON.stringify({cls:document.body.className,"
            "mark:(function(){var e=document.getElementById('collapsedMark');"
            "return e?(!e.hidden):null;})()})"
        )
        info = json.loads(body)
        print(f"拖完后 窗口={x1},{y1} {w1}x{h1} state={st['collapsed']} body={info}", flush=True)

        check("拖到顶边后进入收起状态", st["collapsed"] is True, str(st)[:90])
        check("窗口缩成小条尺寸", (w1, h1) in ((104, 20), (20, 104)), f"{w1}x{h1}")
        check("页面切到小条形态", "is-collapsed" in info["cls"], info["cls"])
        check("三个点的把手显示出来", info["mark"] is True, str(info["mark"]))

        # 点小条展开
        cx, cy = x1 + w1 // 2, y1 + h1 // 2
        user32.SetCursorPos(cx, cy)
        time.sleep(0.1)
        user32.mouse_event(LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.1)
        user32.mouse_event(LEFTUP, 0, 0, 0, 0)
        time.sleep(1.4)

        st2 = json.loads(api.get_window_state())
        x2, y2, w2, h2 = rect(hwnd)
        cls2 = win.evaluate_js("document.body.className")
        check("点小条能展开", st2["collapsed"] is False, str(st2)[:80])
        check("展开回原尺寸", w2 > 300 and h2 > 400, f"{w2}x{h2}")
        check("页面退出小条形态", "is-collapsed" not in cls2, cls2)
        print(f"展开后 {x2},{y2} {w2}x{h2}", flush=True)

        ok = all(r[1] for r in RESULTS)
        print(f"通过 {sum(1 for r in RESULTS if r[1])} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
