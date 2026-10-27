"""拖动验证：标题栏能拖窗口，列表区域拖不动窗口。

为什么必须真鼠标：
DOM 事件只能证明监听器在，证明不了「用户按住标题栏拖动窗口会动」。
这里用 SetCursorPos + mouse_event 发真实输入，再用 GetWindowRect 看窗口
有没有真的跟着走。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-drag-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def rect(hwnd: int):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def client_origin(hwnd: int):
    p = wt.POINT(0, 0)
    user32.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(p))
    return p.x, p.y


def center_of(win, selector: str):
    """页面元素中心点 → 屏幕坐标。"""
    raw = win.evaluate_js(
        "(function(){var e=document.querySelector(%s);"
        "if(!e)return '';var r=e.getBoundingClientRect();"
        "return JSON.stringify([r.left+r.width/2,r.top+r.height/2]);})()"
        % repr(selector).replace("'", '"')
    )
    if not raw:
        return None
    cx, cy = ctypes.c_int(0), ctypes.c_int(0)
    import json
    cx, cy = json.loads(raw)
    ox, oy = client_origin(int(win.native.Handle.ToInt64()))
    return int(ox + cx), int(oy + cy)


def drag(x1: int, y1: int, x2: int, y2: int, steps: int = 12) -> None:
    user32.SetCursorPos(x1, y1)
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.12)
    for i in range(1, steps + 1):
        user32.SetCursorPos(
            int(x1 + (x2 - x1) * i / steps),
            int(y1 + (y2 - y1) * i / steps),
        )
        time.sleep(0.03)
    time.sleep(0.15)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.5)


def main() -> None:
    state = appmod.load_state()
    state.update({"snap": False, "auto_collapse": False, "mode": "mini"})
    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)

    appmod.Store(appmod.DATA_FILE).save([
        {"id": "a", "title": "第一条待办", "priority": "medium", "due": "", "time": "",
         "repeat": "none", "note": "", "done": False, "createdAt": 1},
        {"id": "b", "title": "第二条待办", "priority": "medium", "due": "", "time": "",
         "repeat": "none", "note": "", "done": False, "createdAt": 2},
        {"id": "c", "title": "第三条待办", "priority": "medium", "due": "", "time": "",
         "repeat": "none", "note": "", "done": False, "createdAt": 3},
    ])

    window = webview.create_window(
        "drag", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    def runner() -> None:
        time.sleep(2.8)
        win = webview.windows[0]
        hwnd = int(win.native.Handle.ToInt64())
        win.resize(380, 560)
        time.sleep(0.3)
        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)
        time.sleep(0.6)
        # 摆到一个方便拖的位置
        win.move(500, 300)
        time.sleep(0.6)

        x0, y0, w, h = rect(hwnd)
        print(f"初始窗口: {x0},{y0} {w}x{h}")

        # 1) 标题栏拖动：按下小标题区域空白处，向右下拖 90x50
        drag(x0 + 90, y0 + 16, x0 + 180, y0 + 66)
        x1, y1, _, _ = rect(hwnd)
        print(f"拖标题栏后: {x1},{y1}  位移={x1 - x0},{y1 - y0}")

        # 2) 列表区域拖动：按住第一条待办，向下拖 —— 不该移动窗口
        drag(x1 + 170, y1 + 150, x1 + 170, y1 + 250)
        x2, y2, _, _ = rect(hwnd)
        print(f"拖列表后:   {x2},{y2}  位移={x2 - x1},{y2 - y1}")

        # 3) 点击待办勾选框（真实鼠标），确认能勾上
        before = window.evaluate_js("document.querySelectorAll('.todo-item .check.is-checked').length")
        pt = center_of(win, ".todo-item .check")
        print(f"勾选框屏幕坐标: {pt}")
        if pt:
            drag(pt[0], pt[1], pt[0], pt[1], steps=1)
        time.sleep(0.6)
        after = window.evaluate_js("document.querySelectorAll('.todo-item .check.is-checked').length")
        print(f"勾选：{before} -> {after}")

        # 4) 点底部 + 号，抽屉应展开
        pt2 = center_of(win, "#btnQuickAdd")
        print(f"加号屏幕坐标: {pt2}")
        if pt2:
            drag(pt2[0], pt2[1], pt2[0], pt2[1], steps=1)
        time.sleep(0.6)
        adding = window.evaluate_js("document.body.classList.contains('is-adding')")
        print(f"点 + 后抽屉展开: {adding}")

        ok_title = (abs(x1 - x0) > 40 and abs(y1 - y0) > 20)
        ok_list = (abs(x2 - x1) < 6 and abs(y2 - y1) < 6)
        ok_check = str(after) == '1'
        print(f"RESULT title_drag={ok_title} list_stays={ok_list} check={ok_check} add_sheet={adding}")
        os._exit(0 if (ok_title and ok_list and ok_check and adding) else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
