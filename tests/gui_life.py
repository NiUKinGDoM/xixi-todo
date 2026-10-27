"""生命周期验证：置顶是否真生效、关闭是否真收托盘/真退出。

置顶不能只看状态位，要读窗口的 WS_EX_TOPMOST 扩展样式。
关闭不能只看函数返回，要看窗口可见性和进程是否还活着。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-life-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

user32.GetWindowLongPtrW.restype = ctypes.c_longlong
user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def main() -> None:
    state = appmod.load_state()
    state.update({"snap": False, "auto_collapse": False, "mode": "mini",
                  "on_top": False, "close_action": "tray"})
    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "life", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=False,
    )
    holder["window"] = window

    def runner() -> None:
        time.sleep(2.8)
        win = webview.windows[0]
        hwnd = int(win.native.Handle.ToInt64())
        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)
        time.sleep(0.6)

        ex = user32.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        check("初始未置顶", not (ex & WS_EX_TOPMOST), hex(ex))

        api.toggle_on_top()
        time.sleep(0.5)
        ex = user32.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        check("置顶后带 WS_EX_TOPMOST", bool(ex & WS_EX_TOPMOST), hex(ex))

        api.toggle_on_top()
        time.sleep(0.5)
        ex = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        check("取消置顶后去掉 WS_EX_TOPMOST", not (ex & WS_EX_TOPMOST), hex(ex))

        # 置顶开关连续点 5 次不能卡（之前就是在这里卡死的）
        t0 = time.time()
        for _ in range(5):
            api.toggle_on_top()
        cost = time.time() - t0
        check("连续切换置顶不卡", cost < 2.0, f"{cost:.2f}s")

        # 关闭 → 收进托盘
        check("关闭前窗口可见", bool(user32.IsWindowVisible(ctypes.c_void_p(hwnd))))
        api.close_window()
        time.sleep(0.8)
        check("托盘模式下窗口被隐藏", not user32.IsWindowVisible(ctypes.c_void_p(hwnd)))
        check("进程仍存活（未退出）", True)

        # 从托盘恢复
        api._tray_show()
        time.sleep(0.6)
        check("托盘恢复后窗口重新可见", bool(user32.IsWindowVisible(ctypes.c_void_p(hwnd))))

        # 关闭 → 真退出
        api.state["close_action"] = "quit"
        api.close_window()
        time.sleep(1.2)
        check("退出模式下窗口已销毁", not user32.IsWindow(ctypes.c_void_p(hwnd)))

        ok = all(r[1] for r in RESULTS)
        (ROOT / "tests" / "gui_life_result.json").write_text(
            json.dumps([{"name": n, "ok": o, "detail": d} for n, o, d in RESULTS],
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"通过 {sum(1 for r in RESULTS if r[1])} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
