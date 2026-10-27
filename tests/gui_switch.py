"""设置页开关：用真实鼠标点，验证滑块状态是否真的变化。

DOM 的 .click() 能绕过命中区域问题，所以这里必须发真实输入：
SetCursorPos + mouse_event，点在开关中心，再看 class 变化。
同时测「点在行的文字上」——用户习惯点整行，这两种都要能切。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-sw-")
# 开机自启动要验证真实注册表读写：放行写入，但换一个测试专用值名，
# 不碰用户真正的启动项（XiXiTodo）
REG_NAME = "XiXiTodoProbe"
os.environ["XIXI_TODO_ALLOW_REG"] = "1"
os.environ["XIXI_TODO_REG_NAME"] = REG_NAME

import webview  # noqa: E402
import app as appmod  # noqa: E402

user32 = ctypes.windll.user32
LEFTDOWN = 0x0002
LEFTUP = 0x0004

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def client_origin(hwnd: int):
    p = wt.POINT(0, 0)
    user32.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(p))
    return p.x, p.y


def sxy(win, selector: str):
    raw = win.evaluate_js(
        "(function(){var e=document.querySelector(%s);if(!e)return '';"
        "var r=e.getBoundingClientRect();"
        "return JSON.stringify([r.left+r.width/2,r.top+r.height/2]);})()"
        % json.dumps(selector)
    )
    if not raw:
        return None
    cx, cy = json.loads(raw)
    ox, oy = client_origin(int(win.native.Handle.ToInt64()))
    return int(ox + cx), int(oy + cy)


def click(pt) -> None:
    user32.SetCursorPos(pt[0], pt[1])
    time.sleep(0.1)
    user32.mouse_event(LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(LEFTUP, 0, 0, 0, 0)
    time.sleep(0.55)


def main() -> None:
    state = appmod.load_state()
    state.update({"snap": True, "auto_collapse": True, "collapse_min": True,
                  "mode": "mini", "close_action": "quit"})
    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "sw", url=str(ROOT / "ui" / "index.html"), js_api=api,
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
        time.sleep(0.5)
        win.evaluate_js("document.getElementById('btnSettingsMini').click()")
        time.sleep(0.9)

        def on_of(sel: str) -> bool:
            return bool(win.evaluate_js(
                "document.getElementById(%s).classList.contains('is-on')" % json.dumps(sel)))

        # 逐个开关：点中心 → 状态应翻转 → 再点回来
        # setAutoStart 单独测：它走注册表，用测试专用值名
        for sel in ("setSnap", "setAutoCollapse", "setCollapse", "setTop"):
            # 关掉自动贴边/自动收起，避免点开关时窗口被吸走
            before = on_of(sel)
            pt = sxy(win, "#" + sel)
            if not pt:
                check(f"{sel} 可定位", False, "取不到坐标")
                continue
            local = win.evaluate_js(
                "(function(){var e=document.getElementById(%s);var r=e.getBoundingClientRect();"
                "var cx=r.left+r.width/2, cy=r.top+r.height/2;"
                "var hit=document.elementFromPoint(cx,cy);"
                "return JSON.stringify([Math.round(cx),Math.round(cy),"
                "Math.round(innerWidth),Math.round(innerHeight),"
                "hit?(hit.id||hit.className||hit.tagName):'null']);})()" % json.dumps(sel)
            )
            click(pt)
            after = on_of(sel)
            check(f"点 {sel} 开关状态翻转", after != before, f"屏幕{pt} 页内{local} {before} -> {after}")
            if after != before:
                click(pt)
                check(f"再点 {sel} 恢复", on_of(sel) == before, f"now={on_of(sel)}")

        # 开机自启动：真实写注册表（测试专用值名），开关必须跟着变
        def reg_exists() -> bool:
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, appmod.AUTOSTART_KEY) as k:
                    winreg.QueryValueEx(k, REG_NAME)
                return True
            except Exception:
                return False

        pt = sxy(win, "#setAutoStart")
        before = on_of("setAutoStart")
        click(pt)
        after = on_of("setAutoStart")
        check("点开机自启动开关状态翻转", after != before,
              f"{before} -> {after} 注册表={reg_exists()}")
        check("注册表与开关一致", reg_exists() == after,
              f"开关={after} 注册表={reg_exists()}")
        click(pt)
        check("再点关掉自启动", on_of("setAutoStart") == before and reg_exists() == before,
              f"开关={on_of('setAutoStart')} 注册表={reg_exists()}")

        # 点文字区域也应能切（很多人不会去瞄那个小滑块）
        pt = sxy(win, "#setAutoCollapse")
        row = win.evaluate_js(
            "(function(){var e=document.getElementById('setAutoCollapse');"
            "var r=e.closest('.set-row').getBoundingClientRect();"
            "return JSON.stringify([r.left+70,r.top+r.height/2]);})()"
        )
        if row and pt:
            cx, cy = json.loads(row)
            ox, oy = client_origin(hwnd)
            before = on_of("setAutoCollapse")
            click((int(ox + cx), int(oy + cy)))
            check("点行的文字区也能切换", on_of("setAutoCollapse") != before,
                  f"{before} -> {on_of('setAutoCollapse')}")
        else:
            check("点行的文字区也能切换", False, "取不到坐标")

        ok = all(r[1] for r in RESULTS)
        print(f"通过 {sum(1 for r in RESULTS if r[1])} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
