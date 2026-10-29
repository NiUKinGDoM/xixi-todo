"""探针：WebView2 窗口到底能不能真透明（透出背后的东西）。

背景：pywebview 的 transparent=True 只让 WebView2 不画背景，
但 WinForms 窗体自己还有一层不透明底色，所以只能看到浅灰白边，看不到桌面。

这次把「窗体底色」也处理掉，分三种模式实测：
  plain     只设 Form 底色（对照组：应该看到窗体底色）
  colorkey  Form 底色当色键抠掉（LWA_COLORKEY）
  layeralpha WS_EX_LAYERED + LWA_ALPHA(255)，启用逐像素 alpha（Electron 的做法）

判断依据：垫一层纯青色窗口在探针正下方。
  窗口圆角外侧若显示青色  -> 真透明，桌面（这里是青色底窗）透出来了
  若显示品红              -> 只透出窗体底色，WebView2 那层还是挡着
  若显示白/灰             -> 完全没透
用法：python tests/trans_probe2.py [plain|colorkey|layeralpha]
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

os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-probe-")

import webview  # noqa: E402

MODE = (sys.argv[1] if len(sys.argv) > 1 else "plain").lower()

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]

MAGENTA = 0x00FF00FF  # COLORREF(BGR) -> RGB(255,0,255)
CYAN = 0x00FFFF00     # COLORREF(BGR) -> RGB(0,255,255)

W, H = 360, 300
X, Y = 320, 260

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;background:transparent;overflow:hidden;}
  .card{
    position:absolute;inset:0;border-radius:24px;
    background:rgba(0,0,0,0.5);
    display:grid;place-items:center;
    font:700 16px "Microsoft YaHei",sans-serif;color:#fff;
  }
</style></head><body><div class="card">PROBE</div></body></html>"""

page_dir = Path(tempfile.mkdtemp(prefix="xixi-probe-page-"))
(page_dir / "index.html").write_text(PAGE, encoding="utf-8")

STOP = False
_KEEP = []


def make_bg(x, y, w, h, colorref):
    """纯色无边框底层窗口，用来当「桌面」的替身。"""
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
    cls = "XiXiProbeBg"
    wc = WNDCLASS(0, proc, 0, 0, hinst, None, None, brush, None, cls)
    user32.RegisterClassW(ctypes.byref(wc))
    _KEEP.extend([proc, wc])
    hwnd = user32.CreateWindowExW(
        0, cls, "bg", 0x80000000 | 0x10000000,  # WS_POPUP | WS_VISIBLE
        x, y, w, h, None, None, hinst, None,
    )
    return hwnd


def pump():
    msg = wt.MSG()
    while not STOP:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)


def probe_colors(hwnd):
    from PIL import ImageGrab

    r = wt.RECT()
    user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
    out = {}
    out["corner"] = img.getpixel((6, 6))
    out["center"] = img.getpixel((w // 2, h // 2))
    out["edge_top"] = img.getpixel((w // 2, 3))
    img.save(ROOT / "tests" / ("trans2_%s.png" % MODE))
    return out, (r.left, r.top, w, h)


def worker(window):
    global STOP
    try:
        time.sleep(3.5)
        form = window.native
        hwnd = int(form.Handle.ToInt32())
        print("mode=%s hwnd=%s" % (MODE, hwnd))

        bg = make_bg(X - 40, Y - 40, W + 80, H + 80, CYAN)
        threading.Thread(target=pump, daemon=True).start()

        # 窗体底色设为品红：如果只能看到品红，说明 WebView2 已经透明，
        # 卡住的是 WinForms 这一层。
        try:
            from System.Drawing import Color  # type: ignore

            form.BackColor = Color.FromArgb(255, 0, 255)
            print("form backcolor = magenta")
        except Exception as exc:
            print("backcolor failed", exc)

        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if MODE == "colorkey":
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
            ok = user32.SetLayeredWindowAttributes(hwnd, MAGENTA, 0, 0x1)
            print("colorkey ->", ok)
        elif MODE == "layeralpha":
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
            ok = user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x2)
            print("layeralpha(255) ->", ok)

        # 青色底窗插到探针正下方
        user32.SetWindowPos(ctypes.c_void_p(bg), ctypes.c_void_p(hwnd), 0, 0, 0, 0, 0x0013)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)

        time.sleep(1.6)
        colors, rect = probe_colors(hwnd)
        print("rect", rect)
        for k, v in colors.items():
            print("  %-9s rgba=%s" % (k, v))
        print("判定：corner 青(0,255,255)=真透明 | 品红(255,0,255)=只透窗体底 | 白/灰=没透")
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
        "PROBE2", url=str(page_dir / "index.html"),
        width=W, height=H, x=X, y=Y,
        frameless=True, transparent=True, shadow=False, on_top=True,
        background_color="#000000",
    )
    threading.Thread(target=worker, args=(window,), daemon=True).start()
    webview.start(debug=False)


if __name__ == "__main__":
    main()
