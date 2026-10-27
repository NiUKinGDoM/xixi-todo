"""条目操作按钮：平时不占位，鼠标移上去才浮现并且能点。

CSS :hover 只能靠真实鼠标触发，所以这里用 SetCursorPos 把指针挪到行上，
再读 computed opacity，并真实点一下编辑按钮。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-hover-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

u32 = ctypes.windll.user32
LEFTDOWN, LEFTUP = 0x0002, 0x0004
RESULTS: list[bool] = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def origin(hwnd):
    p = wt.POINT(0, 0)
    u32.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(p))
    return p.x, p.y


def click(x, y):
    u32.SetCursorPos(x, y)
    time.sleep(0.12)
    u32.mouse_event(LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    u32.mouse_event(LEFTUP, 0, 0, 0, 0)
    time.sleep(0.7)


def main():
    st = appmod.load_state()
    st.update({"mode": "mini", "snap": False, "auto_collapse": False})
    holder = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, st)
    appmod.Store(appmod.DATA_FILE).save([
        {"id": "a", "title": "给王工回钛铸件报价单，附上最新的熔模铸造工艺说明", "priority": "high",
         "due": "", "time": "", "repeat": "none", "note": "", "done": False, "createdAt": 1},
        {"id": "b", "title": "第二条", "priority": "medium", "due": "", "time": "",
         "repeat": "none", "note": "", "done": False, "createdAt": 2},
    ])
    window = webview.create_window(
        "hover", url=str(ROOT / "ui" / "index.html"), js_api=api,
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
        win.move(640, 300)
        time.sleep(1.0)
        ox, oy = origin(hwnd)

        # 指针先放到窗口外，确认按钮是隐藏的
        u32.SetCursorPos(10, 10)
        time.sleep(0.5)
        op0 = win.evaluate_js(
            "getComputedStyle(document.querySelector('.todo-actions')).opacity"
        )
        check("未悬停时按钮不可见", float(op0) < 0.1, str(op0))

        # 标题是否铺满（右侧留白小）
        rect = win.evaluate_js(
            "JSON.stringify((function(){var t=document.querySelector('.todo-title');"
            "var m=document.querySelector('.todo-main');"
            "var r=t.getBoundingClientRect(), mr=m.getBoundingClientRect();"
            "return [Math.round(r.width), Math.round(mr.width)];})())"
        )
        tw, mw = json.loads(rect)
        check("标题可用宽度接近整行", tw >= mw - 4, f"title={tw} main={mw}")

        # 真实悬停到第一条
        row_y = win.evaluate_js(
            "Math.round((function(){var r=document.querySelector('.todo-item').getBoundingClientRect();"
            "return r.top + r.height/2;})())"
        )
        u32.SetCursorPos(ox + 200, oy + int(row_y))
        time.sleep(0.7)
        op1 = win.evaluate_js(
            "getComputedStyle(document.querySelector('.todo-actions')).opacity"
        )
        check("悬停后按钮浮现", float(op1) > 0.9, str(op1))

        # 真实点编辑按钮
        pt = win.evaluate_js(
            "JSON.stringify((function(){var b=document.querySelector('.todo-item .edit-btn');"
            "var r=b.getBoundingClientRect();return [Math.round(r.left+r.width/2),"
            "Math.round(r.top+r.height/2)];})())"
        )
        bx, by = json.loads(pt)
        click(ox + bx, oy + by)
        opened = win.evaluate_js("document.getElementById('modalMask').hidden === false")
        check("悬停后能点到编辑", opened is True, str(opened))

        if opened:
            win.evaluate_js("document.getElementById('modalClose').click()")
            time.sleep(0.3)

        # 移开指针，按钮重新隐藏
        u32.SetCursorPos(10, 10)
        time.sleep(0.6)
        op2 = win.evaluate_js(
            "getComputedStyle(document.querySelector('.todo-actions')).opacity"
        )
        check("移开后按钮隐藏", float(op2) < 0.1, str(op2))

        ok = all(RESULTS)
        print(f"通过 {sum(RESULTS)} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
