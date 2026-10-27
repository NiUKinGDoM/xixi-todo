"""【实验性脚本，未纳入 run_tests.bat】

真实窗口里用 evaluate_js 驱动形态切换。

⚠️ 已知问题：本脚本在某些时序下会挂死。原因是 pywebview 的
`window.width` 属性内部会 `events.shown.wait(15)`，透明无边框窗口下
该事件不稳定，且 evaluate_js 与 js_api 回调并发时可能互相等待
（看门狗线程也未能触发，疑似 GIL 级阻塞）。

已验证可用的替代方案：
  - 逻辑层：test_window.py（假窗口对象，33 项，稳定）
  - 真实点击：tests/click_mode.py（ALT 解锁前台 + mouse_event，实测通过）

保留此文件仅作参考，勿用于 CI。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import webview  # noqa: E402

from app import FULL_H, FULL_W, MINI_H, MINI_W, Api, Store, save_state  # noqa: E402

RESULTS: list[str] = []
TITLE = "形态测试"

user32 = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(("OK   " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""))


def find_window(title: str) -> int:
    hits: list[int] = []

    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        if n == 0:
            return True
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, b, n + 1)
        if title in b.value:
            hits.append(h)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return hits[0] if hits else 0


def win_size(hwnd: int) -> tuple[int, int]:
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def watchdog(seconds: int) -> None:
    time.sleep(seconds)
    print("\n!! 看门狗超时触发，强制退出", flush=True)
    for r in RESULTS:
        print(r, flush=True)
    os._exit(9)


def main() -> int:
    threading.Thread(target=watchdog, args=(70,), daemon=True).start()

    store = Store(ROOT / "tests" / "mode_real_todos.json")
    holder: dict = {}
    state = {
        "mode": "mini",
        "on_top": True,
        "mini": {"x": 260, "y": 220, "w": MINI_W, "h": MINI_H},
        "full": {"x": 160, "y": 120, "w": FULL_W, "h": FULL_H},
    }
    api = Api(store, holder, state)

    index = ROOT / "ui" / "index.html"
    window = webview.create_window(
        TITLE,
        url=str(index),
        js_api=api,
        width=MINI_W,
        height=MINI_H,
        min_size=(320, 420),
        frameless=True,
        easy_drag=True,
        transparent=True,
        shadow=False,
        on_top=True,
        text_select=True,
    )
    holder["window"] = window

    def on_shown() -> None:
        try:
            window.resize(MINI_W, MINI_H)
            window.move(260, 220)
        except Exception as exc:
            print("on_shown error:", exc, flush=True)

    window.events.shown += on_shown

    def run() -> None:
        try:
            time.sleep(4.0)
            hwnd = find_window(TITLE)
            check("找到真实窗口", hwnd != 0, f"hwnd={hwnd}")
            if not hwnd:
                return

            w, h = win_size(hwnd)
            check(
                f"迷你模式实际尺寸为 {MINI_W}x{MINI_H}",
                abs(w - MINI_W) <= 4 and abs(h - MINI_H) <= 4,
                f"实测 {w}x{h}",
            )

            # 模拟用户点击界面上的「切换到完整视图」按钮，
            # 走完整链路：JS click → api.set_mode → Python resize → JS 回写 class
            window.evaluate_js("document.getElementById('btnMode').click()")
            time.sleep(2.5)
            hwnd2 = find_window(TITLE)
            w2, h2 = win_size(hwnd2)
            check(
                f"切到完整模式实际尺寸为 {FULL_W}x{FULL_H}",
                abs(w2 - FULL_W) <= 6 and abs(h2 - FULL_H) <= 6,
                f"实测 {w2}x{h2}",
            )

            cls = window.evaluate_js("document.body.className")
            check("界面切到 mode-full", "mode-full" in (cls or ""), f"class={cls}")

            sidebar = window.evaluate_js(
                "getComputedStyle(document.querySelector('.sidebar')).display"
            )
            check("完整模式侧边栏可见", sidebar != "none", f"display={sidebar}")

            window.evaluate_js("document.getElementById('btnMode').click()")
            time.sleep(2.5)
            hwnd3 = find_window(TITLE)
            w3, h3 = win_size(hwnd3)
            check(
                f"切回迷你实际尺寸为 {MINI_W}x{MINI_H}",
                abs(w3 - MINI_W) <= 4 and abs(h3 - MINI_H) <= 4,
                f"实测 {w3}x{h3}",
            )

            cls2 = window.evaluate_js("document.body.className")
            check("界面切回 mode-mini", "mode-mini" in (cls2 or ""), f"class={cls2}")

            chips = window.evaluate_js(
                "getComputedStyle(document.getElementById('filterChips')).display"
            )
            check("迷你模式筛选胶囊可见", chips == "flex", f"display={chips}")

            # 置顶开关：同样走界面按钮
            window.evaluate_js("document.getElementById('btnPin').click()")
            time.sleep(1.5)
            check("置顶状态已写入", state["on_top"] is False, f"on_top={state['on_top']}")
            pin_on = window.evaluate_js(
                "document.getElementById('btnPin').classList.contains('is-on')"
            )
            check("图钉按钮回到未激活态", pin_on is False, f"is-on={pin_on}")

        except Exception as exc:  # noqa: BLE001
            check("真实窗口测试执行", False, repr(exc))
        finally:
            try:
                window.destroy()
            except Exception:
                pass

    threading.Thread(target=run, daemon=True).start()

    webview.start()

    time.sleep(0.5)
    print("\n===== 真实窗口形态测试 =====", flush=True)
    for r in RESULTS:
        print(r, flush=True)
    failed = [r for r in RESULTS if r.startswith("FAIL")]
    print(f"\n通过 {len(RESULTS) - len(failed)} / {len(RESULTS)}", flush=True)

    try:
        tmp = ROOT / "tests" / "mode_real_todos.json"
        if tmp.exists():
            tmp.unlink()
    except Exception:
        pass

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
