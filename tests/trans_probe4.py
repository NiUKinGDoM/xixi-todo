"""探针 4：色键透明能透，但窗口点不动（分层窗口按像素 alpha 做命中测试，
半透明处被当成"穿透"）。这里换一种做法：

  Form 底色设成 alpha=0 的透明色，让窗口表面的 alpha 直接来自 WebView2 内容，
  再用 LWA_ALPHA(255) 打开逐像素合成。

要验两件事：
  1) 圆角外侧还能不能透出底窗（透明有没有丢）
  2) 卡片正中间 WindowFromPoint 能不能命中自己的窗口（点击有没有救回来）
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-probe4-")

import webview  # noqa: E402

MODE = (sys.argv[1] if len(sys.argv) > 1 else "alpha0").lower()

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]

KEY = 0x00FE00FF
CYAN = 0x00FFFF00
W, H = 340, 280
X, Y = 420, 320

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;background:transparent;overflow:hidden;}
  .card{position:absolute;inset:0;border-radius:24px;background:rgba(255,255,255,0.8);
        display:grid;place-items:center;font:700 16px "Microsoft YaHei";color:#111;}
</style></head><body><div class="card">PROBE4</div></body></html>"""

page_dir = Path(tempfile.mkdtemp(prefix="xixi-probe4-page-"))
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
    cls = "XiXiProbe4Bg"
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
        time.sleep(3.2)
        form = window.native
        hwnd = int(form.Handle.ToInt32())
        bg = make_bg(X - 60, Y - 60, W + 120, H + 120, CYAN)
        threading.Thread(target=pump, daemon=True).start()

        from System.Drawing import Color  # type: ignore

        if MODE == "alpha0":
            form.BackColor = Color.FromArgb(0, 255, 0, 255)   # 全透明底色
        else:
            form.BackColor = Color.FromArgb(255, 255, 0, 254)  # 不透明键色

        ex = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, ex | 0x00080000)
        if MODE == "alpha0":
            ok = user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x2)  # LWA_ALPHA
        else:
            ok = user32.SetLayeredWindowAttributes(hwnd, KEY, 0, 0x1)  # LWA_COLORKEY
        print(MODE, "layered ->", ok)

        user32.SetWindowPos(ctypes.c_void_p(bg), ctypes.c_void_p(hwnd), 0, 0, 0, 0, 0x0013)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)
        time.sleep(1.5)

        r = wt.RECT()
        user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        cx, cy = r.left + w // 2, r.top + h // 2

        from PIL import ImageGrab

        img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
        img.save(ROOT / "tests" / ("probe4_%s.png" % MODE))
        print("corner", img.getpixel((6, 6)), "center", img.getpixel((w // 2, h // 2)))

        for label, (px, py) in (("center", (cx, cy)), ("corner", (r.left + 4, r.top + 4))):
            hit = user32.WindowFromPoint(wt.POINT(px, py))
            print("  hit@%s -> %s (self=%s, bg=%s)" % (label, hit, hit == hwnd, hit == bg))
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
        "PROBE4", url=str(page_dir / "index.html"),
        width=W, height=H, x=X, y=Y,
        frameless=True, transparent=True, shadow=False, on_top=True,
        background_color="#000000",
    )
    threading.Thread(target=worker, args=(window,), daemon=True).start()
    webview.start(debug=False)


if __name__ == "__main__":
    main()
