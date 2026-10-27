"""验证：DWM 逐像素透明 + WebView2 能否得到抗锯齿圆角。

思路：pywebview 的 transparent=True 只设了 WebView2 的透明背景，
但 WinForms 窗体本身仍是不透明底色，所以页面透明处会露出窗体底色。
如果再用 DwmExtendFrameIntoClientArea(-1) 把整个客户区当玻璃，
并把窗体底色设为黑（DWM 玻璃里黑色=全透明），就能拿到逐像素 alpha，
CSS 画的圆角自然带上抗锯齿。
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

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;background:transparent;}
  .card{
    position:absolute;inset:0;border-radius:22px;
    background:linear-gradient(150deg,#ffffff 0%,#eef2ff 60%,#f7eefb 100%);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.9);
    display:grid;place-items:center;
    font:600 14px "Microsoft YaHei",sans-serif;color:#2a3350;
  }
</style></head><body><div class="card">PROBE</div></body></html>"""

html_path = Path(tempfile.mkdtemp(prefix="xixi-probe-page-")) / "index.html"
html_path.write_text(PAGE, encoding="utf-8")

DWM = ctypes.windll.dwmapi


class _MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def extend_frame(hwnd: int) -> int:
    m = _MARGINS(-1, -1, -1, -1)
    return DWM.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))


def main() -> None:
    window = webview.create_window(
        "PROBE",
        url=str(html_path),
        width=380,
        height=560,
        frameless=True,
        transparent=True,
        shadow=False,
        on_top=True,
        background_color="#000000",
    )

    def worker():
        time.sleep(4.0)
        try:
            form = window.native
            hwnd = int(form.Handle.ToInt32())
            print("hwnd", hwnd)

            # 窗体底色设黑：DWM 玻璃下黑色即完全透明
            try:
                from System.Drawing import Color  # type: ignore

                form.BackColor = Color.Black
                print("BackColor=Black OK")
            except Exception as exc:
                print("set backcolor failed", exc)

            rc = extend_frame(hwnd)
            print("DwmExtendFrameIntoClientArea ->", rc)

            try:
                form.Refresh()
            except Exception:
                pass

            time.sleep(1.2)
            from PIL import ImageGrab

            r = wt.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
            out = ROOT / "tests" / "probe_transparent.png"
            ImageGrab.grab(bbox=(r.left - 20, r.top - 20, r.right + 20, r.bottom + 20)).save(out)
            print("saved", out, r.left, r.top, r.right - r.left, r.bottom - r.top)
        except Exception as exc:
            print("worker error", repr(exc))
        finally:
            try:
                window.destroy()
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()
    webview.start(debug=False)


if __name__ == "__main__":
    main()
