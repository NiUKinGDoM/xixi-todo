"""真实点击验证「小卡片 ⇄ 完整视图」按钮。

完全模拟用户操作：ALT 解锁前台 → 点击按钮 → 从外部量窗口尺寸。
不依赖 pywebview 的任何 evaluate_js / window 属性，避免线程陷阱。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys
import time

user32 = ctypes.windll.user32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
TITLE = "待办事项"

user32 = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def find_window() -> int:
    hits: list[int] = []

    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        if n == 0:
            return True
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, b, n + 1)
        if TITLE in b.value:
            hits.append(h)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return hits[0] if hits else 0


def rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def focus(hwnd: int) -> bool:
    user32.keybd_event(0x12, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.25)
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.6)
    return user32.GetForegroundWindow() == hwnd


def click(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.25)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def main() -> int:
    hwnd = find_window()
    if not hwnd:
        print("NO_WINDOW")
        return 1

    x, y, w, h = rect(hwnd)
    print(f"初始: 位置 {x},{y} 尺寸 {w}x{h}")
    print(f"前台: {focus(hwnd)}")

    # 迷你标题栏按钮：4 个 26px 按钮 + 右内边距 8，从卡片右缘往左推
    # btnMode 是第 2 个（从右数第 3 个）
    card_w = w - 24           # body padding 12 * 2
    right_pad = 8
    btn_w, gap = 26, 2
    # 从右往左：close, min, mode, pin
    mode_center_from_right = right_pad + btn_w * 1.5 + gap * 2   # 约 8+39+4
    bw = int(card_w - mode_center_from_right)
    bh = 30                    # 标题栏中心（12 内边距 + 18）

    print(f"点击窗口内 ({bw}, {bh}) → 屏幕 ({x + bw}, {y + bh})")
    click(x + bw, y + bh)
    time.sleep(3.0)

    hwnd2 = find_window()
    x2, y2, w2, h2 = rect(hwnd2)
    print(f"点击后: 位置 {x2},{y2} 尺寸 {w2}x{h2}")

    ok = w2 > w + 200
    print(f"结果: {'已展开为完整视图 ✓' if ok else '尺寸未变化 ✗'}")

    if ok:
        # 再点一次收起（完整模式按钮位置不同，在宽窗口的右上角）
        print("\n尝试收起：完整模式按钮位于窗口右上角")
        # 完整模式 minibar 高度 30，右内边距 10；同样 4 个按钮
        bw2 = int(w2 - 10 - (btn_w * 4 + gap * 3) + btn_w * 1.5 + gap)
        click(x2 + bw2, y2 + 15)
        time.sleep(3.0)
        hwnd3 = find_window()
        _, _, w3, h3 = rect(hwnd3)
        print(f"收起后尺寸: {w3}x{h3}")
        print(f"结果: {'已收成小卡片 ✓' if w3 < 500 else '未收起 ✗'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
