"""探针 3：色键透明已经确认能让桌面透出来，这里只看「边缘质量」。

对比两版：
  dwm  交给 DWM 原生圆角（CSS 不做 border-radius），角落是系统抗锯齿
  css  自己做 border-radius，角落像素是「卡片色 + 品红键色」的混合（可能泛紫）

顺带看半透明卡片叠加在有色底窗上的观感。
用法：python tests/trans_probe3.py [dwm|css]
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

os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-probe3-")

import webview  # noqa: E402

MODE = (sys.argv[1] if len(sys.argv) > 1 else "dwm").lower()

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]

KEY = 0x00FE00FF  # COLORREF(BGR) -> RGB(255,0,254)，挑一个 UI 里绝不会出现的颜色
CYAN = 0x00FFFF00

W, H = 360, 300
X, Y = 360, 300

RADIUS = "0" if MODE == "dwm" else "24px"

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%%;background:transparent;overflow:hidden;}
  .card{
    position:absolute;inset:0;border-radius:%s;
    background:rgba(255,255,255,0.66);
    padding:18px;box-sizing:border-box;
    font:600 15px/1.6 "Microsoft YaHei",sans-serif;color:#1b2137;
  }
</style></head><body>
  <div class="card">半透明卡片<br>如果这行字清晰<br>背后能透出颜色，就成了。</div>
</body></html>""" % RADIUS

page_dir = Path(tempfile.mkdtemp(prefix="xixi-probe3-page-"))
(page_dir / "index.html").write_text(PAGE, encoding="utf-8")

STOP = False
_KEEP = []


def make_bg(x, y, w, h, colorref):
    hinst = ctypes.windll.kernel32.GetModuleHandleW(None)
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    @WNDPROC
    def proc(h, msg, wp, lp):
        return user32.DefWindowProcW(h, msg, wp, lp)

    class WNDCLASS(ctypes.Structure):
        _fields_ = [
            ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
            ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
            ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
            ("lpszClassName", wt.LPCWSTR),
        ]

    brush = gdi32.CreateSolidBrush(colorref)
    cls = "XiXiProbe3Bg"
    wc = WNDCLASS(0, proc, 0, 0, hinst, None, None, brush, None, cls)
    user32.RegisterClassW(ctypes.byref(wc))
    _KEEP.extend([proc, wc])
    return user32.CreateWindowExW(
        0, cls, "bg", 0x80000000 | 0x10000000,
        x, y, w, h, None, None, hinst, None,
    )


def pump():
    msg = wt.MSG()
    while not STOP:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)


def worker(window):
    global STOP
    try:
        time.sleep(3.5)
        form = window.native
        hwnd = int(form.Handle.ToInt32())

        bg = make_bg(X - 60, Y - 60, W + 120, H + 120, CYAN)
        threading.Thread(target=pump, daemon=True).start()

        from System.Drawing import Color  # type: ignore

        form.BackColor = Color.FromArgb(255, 0, 254)

        ex = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, ex | 0x00080000)
        ok = user32.SetLayeredWindowAttributes(hwnd, KEY, 0, 0x1)
        print("colorkey ->", ok)

        # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
        v = ctypes.c_int(2)
        rc = dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 33, ctypes.byref(v), 4)
        print("corner round ->", rc)

        user32.SetWindowPos(ctypes.c_void_p(bg), ctypes.c_void_p(hwnd), 0, 0, 0, 0, 0x0013)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)

        time.sleep(1.8)
        from PIL import ImageGrab

        r = wt.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        img = ImageGrab.grab(bbox=(r.left - 10, r.top - 10, r.right + 10, r.bottom + 10))
        out = ROOT / "tests" / ("trans3_%s.png" % MODE)
        img.save(out)
        print("saved", out, img.size)
        for p in [(10, 10), (12, 12), (14, 14), (18, 18), (24, 24), (img.size[0] // 2, img.size[1] // 2)]:
            print("  %s -> %s" % (p, img.getpixel(p)))
    except Exception as exc:
        print("worker error", repr(exc))
    finally:
        STOP = True
        try:
            window.destroy()
        except Exception:
            pass


def main():
    window = webview.create_window(
        "PROBE3", url=str(page_dir / "index.html"),
        width=W, height=H, x=X, y=Y,
        frameless=True, transparent=True, shadow=False, on_top=True,
        background_color="#000000",
    )
    threading.Thread(target=worker, args=(window,), daemon=True).start()
    webview.start(debug=False)


if __name__ == "__main__":
    main()
