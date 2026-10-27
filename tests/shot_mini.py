"""小卡片视觉验收截图：常态 + 添加抽屉展开。

用 PrintWindow 抓真实渲染结果（被遮挡也能抓到），存成 PNG。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-shot-")

import webview  # noqa: E402
import app as appmod  # noqa: E402
from PIL import Image  # noqa: E402

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0

OUT = Path(__file__).resolve().parent


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def grab(hwnd: int, path: Path) -> bool:
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    if not user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT):
        user32.PrintWindow(hwnd, mem, 0)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1).convert("RGB").save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    return True


def main() -> None:
    state = appmod.load_state()
    state.update({"snap": False, "auto_collapse": False, "mode": "mini", "app_name": "xixiの待办"})
    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)

    # 播种几条数据，才看得出列表密度
    store = appmod.Store(appmod.DATA_FILE)
    store.save([
        {"id": "t1", "title": "给王工回钛铸件报价单", "priority": "high", "due": "", "time": "",
         "repeat": "none", "note": "", "done": False, "createdAt": 1},
        {"id": "t2", "title": "整理本周客户拜访记录", "priority": "medium", "due": "2026-10-28",
         "time": "14:00", "repeat": "weekly", "note": "", "done": False, "createdAt": 2},
        {"id": "t3", "title": "每天跟进熔模铸造进度", "priority": "medium", "due": "2026-10-27",
         "time": "", "repeat": "daily", "note": "", "done": False, "createdAt": 3},
        {"id": "t4", "title": "把上周的发货单归档", "priority": "low", "due": "", "time": "",
         "repeat": "none", "note": "", "done": True, "createdAt": 4},
    ])

    window = webview.create_window(
        "shot", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    def runner() -> None:
        time.sleep(2.8)
        hwnd = int(webview.windows[0].native.Handle.ToInt64())
        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)
        time.sleep(0.5)
        grab(hwnd, OUT / "shot_mini.png")

        window.evaluate_js("document.getElementById('btnQuickAdd').click()")
        time.sleep(0.9)
        grab(hwnd, OUT / "shot_mini_add.png")

        # 抽屉里选「每周」，看强调态
        window.evaluate_js(
            "var s=document.getElementById('inputRepeat');"
            "s.value='weekly';s.dispatchEvent(new Event('change'));"
            "document.getElementById('inputDate').value='2026-10-30';"
            "document.getElementById('inputDate').dispatchEvent(new Event('change'));"
            "document.getElementById('inputText').value='每周五汇总订单';"
        )
        time.sleep(0.7)
        grab(hwnd, OUT / "shot_mini_add2.png")

        window.evaluate_js("document.body.classList.remove('is-adding');"
                           "document.getElementById('btnSettingsMini').click()")
        time.sleep(0.9)
        grab(hwnd, OUT / "shot_settings.png")

        # 完整视图 + 设置页：确认顶栏不会压在设置页上
        window.evaluate_js("document.getElementById('setBack').click()")
        time.sleep(0.4)
        window.evaluate_js("document.getElementById('btnMode').click()")
        time.sleep(1.4)
        grab(hwnd, OUT / "shot_full.png")
        window.evaluate_js("document.getElementById('btnSettings').click()")
        time.sleep(0.9)
        grab(hwnd, OUT / "shot_full_settings.png")

        # 小卡片里打开编辑弹窗
        window.evaluate_js("document.getElementById('setBack').click()")
        time.sleep(0.4)
        window.evaluate_js("document.getElementById('btnMode').click()")
        time.sleep(1.4)
        window.evaluate_js("document.querySelector('.todo-item .icon-btn').click()")
        time.sleep(0.8)
        grab(hwnd, OUT / "shot_modal.png")
        os._exit(0)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
