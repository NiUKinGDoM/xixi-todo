"""卡片底色浓度：滑块调到 0 时底色应当消失，文字对比度保持不变。

整窗 alpha 在 WebView2 上验证过是无效的（DirectComposition 不经过 GDI 合成），
所以这里改用纯 CSS 变量，并且必须验证「真的变色」而不只是改了变量值。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-ca-")

import webview  # noqa: E402
import app as appmod  # noqa: E402
from PIL import Image  # noqa: E402

u32 = ctypes.windll.user32
g32 = ctypes.windll.gdi32
RESULTS: list[bool] = []


class BIH(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BI(ctypes.Structure):
    _fields_ = [("bmiHeader", BIH), ("bmiColors", wt.DWORD * 3)]


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def grab(hwnd):
    r = wt.RECT()
    u32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = u32.GetDC(0)
    mem = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, w, h)
    g32.SelectObject(mem, bmp)
    g32.BitBlt(mem, 0, 0, w, h, hdc, r.left, r.top, 0x00CC0020)
    bi = BI()
    bi.bmiHeader.biSize = ctypes.sizeof(BIH)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1).convert("RGB")
    g32.DeleteObject(bmp)
    g32.DeleteDC(mem)
    u32.ReleaseDC(0, hdc)
    return img


def sample(img, pt):
    return img.getpixel(pt)


def main():
    st = appmod.load_state()
    st.update({"mode": "mini", "snap": False, "auto_collapse": False, "card_alpha": 100})
    holder = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, st)
    appmod.Store(appmod.DATA_FILE).save([
        {"id": "a", "title": "给王工回钛铸件报价单", "priority": "high", "due": "", "time": "",
         "repeat": "none", "note": "", "done": False, "createdAt": 1},
    ])
    window = webview.create_window(
        "ca", url=str(ROOT / "ui" / "index.html"), js_api=api,
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
        win.move(700, 300)
        time.sleep(1.0)

        full = grab(hwnd)
        # 取一块「列表空白处」的像素：底部进度条上方、条目之外
        blank_pt = (full.width // 2, full.height - 70)
        text_pt = (26, 30)   # 标题栏文字附近
        base_blank = sample(full, blank_pt)
        print("100% 空白处像素:", base_blank, flush=True)

        # 拖到 0
        win.evaluate_js(
            "var r=document.getElementById('setCardAlpha');"
            "r.value='0';r.dispatchEvent(new Event('input',{bubbles:true}));"
            "r.dispatchEvent(new Event('change',{bubbles:true}));"
        )
        time.sleep(1.0)
        zero = grab(hwnd)
        zero_blank = sample(zero, blank_pt)
        print("0% 空白处像素:", zero_blank, flush=True)

        # 底色从白变成画布色（#f4f6fa → 更暗），应当能测出差异
        diff = sum(abs(a - b) for a, b in zip(base_blank, zero_blank))
        check("调到 0% 底色确实变了", diff >= 6, f"{base_blank} -> {zero_blank} diff={diff}")

        # 文字区域不能被一起冲淡：取标题文字所在行，暗像素（文字）依然存在
        # 用条目卡片区域做对比，它保持白底
        item_pt = (full.width // 2, 150)
        item_zero = sample(zero, item_pt)
        check("条目卡片仍是白底", item_zero[0] > 235 and item_zero[1] > 235,
              str(item_zero))

        # 后端状态
        st_now = json.loads(api.get_window_state())
        check("状态记为 0", st_now.get("card_alpha") == 0, str(st_now.get("card_alpha")))
        saved = json.loads(appmod.STATE_FILE.read_text("utf-8"))
        check("已落盘", saved.get("card_alpha") == 0, str(saved.get("card_alpha")))

        # 调回 100
        win.evaluate_js(
            "var r=document.getElementById('setCardAlpha');"
            "r.value='100';r.dispatchEvent(new Event('input',{bubbles:true}));"
            "r.dispatchEvent(new Event('change',{bubbles:true}));"
        )
        time.sleep(0.8)
        back = grab(hwnd)
        back_blank = sample(back, blank_pt)
        check("调回 100% 恢复白色", sum(abs(a - b) for a, b in zip(back_blank, base_blank)) <= 4,
              f"{back_blank} vs {base_blank}")

        ok = all(RESULTS)
        print(f"通过 {sum(RESULTS)} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
