"""检查更新按钮：真实鼠标点下去必须立刻有反馈，连点不能丢。

以前的问题：开机那次静默检查要跑好几秒，这期间点「检查更新」会被
`if (updateState.checking) return` 直接吞掉 —— 没转圈、没文案、没提示，
用户只能连点。这个脚本用真实输入复现那条路径并验证修复。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-chk-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

user32 = ctypes.windll.user32
LEFTDOWN = 0x0002
LEFTUP = 0x0004

RESULTS: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
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


def press(pt) -> None:
    """按下就松，中间不加长停顿 —— 模拟人手快速连点。"""
    user32.SetCursorPos(pt[0], pt[1])
    time.sleep(0.05)
    user32.mouse_event(LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.04)
    user32.mouse_event(LEFTUP, 0, 0, 0, 0)


def ui(win, js: str):
    return win.evaluate_js(js)


def main() -> None:
    state = appmod.load_state()
    state.update({"mode": "mini", "snap": False, "auto_collapse": False})
    holder = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "chk", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    def runner():
        time.sleep(3)
        win = webview.windows[0]
        hwnd = int(win.native.Handle.ToInt64())
        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)
        win.resize(380, 560)
        time.sleep(0.8)

        ui(win, "document.getElementById('btnSettingsMini').click()")
        time.sleep(0.9)
        ui(win, "document.getElementById('menuUpdate').scrollIntoView({block:'center'})")
        time.sleep(0.4)

        # 先把「开机自动检查」的那次任务人为占住，复现用户遇到的竞态
        ui(win, "window.__todoApp.getUpdateState().checking = true;"
                "window.__todoApp.getUpdateState().task = new Promise(function(){});")

        pt = sxy(win, "#menuUpdate")
        check("更新行可定位", pt is not None, str(pt))
        if not pt:
            print("通过 0 / 1", flush=True)
            os._exit(1)

        press(pt)
        time.sleep(0.25)
        label = ui(win, "document.getElementById('updateLabel').textContent")
        spinning = ui(win, "document.getElementById('menuUpdate').classList.contains('is-checking')")
        check("点下去立刻显示「检查中…」", label == "检查中…", f"label={label}")
        check("图标进入转圈状态", spinning is True, str(spinning))

        # 连点第二下：不能把状态搞乱，也不能报错
        press(pt)
        time.sleep(0.25)
        label2 = ui(win, "document.getElementById('updateLabel').textContent")
        check("连点第二下仍是检查中", label2 == "检查中…", f"label={label2}")

        # 放开卡住的任务，让它真跑一次
        ui(win, "var s=window.__todoApp.getUpdateState();"
                "s.checking=false; s.task=null; s.hasUpdate=false; s.latest=null;")
        press(pt)
        time.sleep(0.3)
        check("重新点击后开始真检查",
              ui(win, "document.getElementById('updateLabel').textContent") == "检查中…")

        # 最多等 10 秒出结果（四个源并行，单个超时 4.5 秒）
        deadline = time.time() + 12
        final = ""
        while time.time() < deadline:
            time.sleep(0.5)
            st = json.loads(ui(win, "JSON.stringify({c:window.__todoApp.getUpdateState().checking})"))
            if not st["c"]:
                final = ui(win, "document.getElementById('updateLabel').textContent")
                break
        check("检查会结束，不会一直卡在检查中", final != "", f"label={final}")
        check("结束后文案恢复正常", final in ("检查更新",) or final.startswith("发现新版本"),
              f"label={final}")
        stuck = ui(win, "document.getElementById('menuUpdate').classList.contains('is-checking')")
        check("转圈状态已清掉", stuck is False, str(stuck))

        ok = all(RESULTS)
        print(f"通过 {sum(RESULTS)} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
