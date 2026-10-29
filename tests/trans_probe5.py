"""探针 5：Windows 11 原生亚克力（DWM system backdrop）。

前两条路都废了：
  LWA_ALPHA  -> WebView2 内容不参与窗口表面，看不出透明
  LWA_COLORKEY -> 能透，但整个窗口的命中测试没了，点什么都没反应

剩下的正路是 DWM 自己的 backdrop：窗口不要 GDI surface（NOREDIRECTIONBITMAP），
DWM 就会把亚克力/云母直接铺在客户区底下，命中测试完全正常。
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-probe5-")

import webview  # noqa: E402

BACKDROP = (sys.argv[1] if len(sys.argv) > 1 else "acrylic").lower()
# 38 = DWMWA_SYSTEMBACKDROP_TYPE
# 2 = DWMSBT_MAINWINDOW(mica) 3 = DWMSBT_TRANSIENTWINDOW(acrylic) 4 = DWMSBT_TABBEDWINDOW
VALUE = {"mica": 2, "acrylic": 3, "tabbed": 4, "none": 1}.get(BACKDROP, 3)

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

W, H = 340, 280
X, Y = 420, 320

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;background:transparent;overflow:hidden;}
  .card{position:absolute;inset:0;border-radius:24px;background:rgba(255,255,255,0.55);
        padding:16px;box-sizing:border-box;
        font:600 15px/1.7 "Microsoft YaHei";color:#101528;}
</style></head><body>
<div class="card">亚克力探针<br>背后的桌面应该被虚化<br>文字必须清楚</div>
</body></html>"""

page_dir = Path(tempfile.mkdtemp(prefix="xixi-probe5-page-"))
(page_dir / "index.html").write_text(PAGE, encoding="utf-8")


def worker(window):
    try:
        time.sleep(3.2)
        form = window.native
        hwnd = int(form.Handle.ToInt32())

        # 关键：去掉 GDI 重定向表面，DWM 才会把 backdrop 铺过来
        ex = user32.GetWindowLongW(ctypes.c_void_p(hwnd), -20)
        user32.SetWindowLongW(ctypes.c_void_p(hwnd), -20, ex | 0x00200000)
        print("ex before", hex(ex), "after", hex(ex | 0x00200000))

        # 把窗体底色设黑：DWM 扩展框架里黑色即全透明
        try:
            from System.Drawing import Color  # type: ignore
            form.BackColor = Color.Black
        except Exception as exc:
            print("backcolor", exc)

        class MARGINS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int),
                        ("t", ctypes.c_int), ("b", ctypes.c_int)]

        m = MARGINS(-1, -1, -1, -1)
        rc0 = dwmapi.DwmExtendFrameIntoClientArea(ctypes.c_void_p(hwnd), ctypes.byref(m))
        print("extend frame ->", rc0)

        v = ctypes.c_int(VALUE)
        rc = dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 38, ctypes.byref(v), 4)
        print("backdrop", BACKDROP, VALUE, "->", rc)

        rc2 = dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), 33, ctypes.byref(ctypes.c_int(2)), 4)
        print("corner round ->", rc2)

        # 让 DWM 重建一次表面
        user32.ShowWindow(ctypes.c_void_p(hwnd), 0)
        time.sleep(0.25)
        user32.ShowWindow(ctypes.c_void_p(hwnd), 9)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)
        time.sleep(1.6)

        from PIL import ImageGrab

        r = wt.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        img = ImageGrab.grab(bbox=(r.left - 24, r.top - 24, r.right + 24, r.bottom + 24))
        img.save(ROOT / "tests" / ("probe5_%s.png" % BACKDROP))
        w = r.right - r.left
        print("center px", ImageGrab.grab(
            bbox=(r.left + 4, r.top + 4, r.left + 40, r.top + 40)).getpixel((18, 18)))
        hit = user32.WindowFromPoint(wt.POINT(r.left + w // 2, r.top + (r.bottom - r.top) // 2))
        print("hit center ->", hit, "self=", hit == hwnd)
    except Exception as exc:
        print("worker error", repr(exc))
    finally:
        try:
            window.destroy()
        except Exception:
            pass


def main():
    window = webview.create_window(
        "PROBE5", url=str(page_dir / "index.html"),
        width=W, height=H, x=X, y=Y,
        frameless=True, transparent=True, shadow=False, on_top=True,
        background_color="#000000",
    )
    threading.Thread(target=worker, args=(window,), daemon=True).start()
    webview.start(debug=False)


if __name__ == "__main__":
    main()
