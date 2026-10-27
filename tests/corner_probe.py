"""验证 Windows 11 原生圆角（DWMWA_WINDOW_CORNER_PREFERENCE）对无边框窗口是否生效。

如果生效，DWM 会用抗锯齿绘制圆角，还自带系统投影，
比 SetWindowRgn 的二值遮罩平滑得多。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-probe2-")

import webview  # noqa: E402

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;background:#eef1f8;}
  .card{position:absolute;inset:0;
    background:linear-gradient(150deg,#ffffff 0%,#eef2ff 60%,#f7eefb 100%);
    display:grid;place-items:center;font:600 14px "Microsoft YaHei",sans-serif;color:#2a3350;}
</style></head><body><div class="card">PROBE2</div></body></html>"""

html_path = Path(tempfile.mkdtemp(prefix="xixi-probe2-page-")) / "index.html"
html_path.write_text(PAGE, encoding="utf-8")

DWM = ctypes.windll.dwmapi
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DEFAULT = 0
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWCP_ROUNDSMALL = 3


def set_corner(hwnd: int, pref: int) -> int:
    val = ctypes.c_int(pref)
    return DWM.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(val), 4)


def main() -> None:
    window = webview.create_window(
        "PROBE2",
        url=str(html_path),
        width=380,
        height=560,
        frameless=True,
        transparent=False,
        shadow=True,
        on_top=True,
        background_color="#EEF1F8",
    )

    def worker():
        time.sleep(4.0)
        try:
            form = window.native
            hwnd = int(form.Handle.ToInt32())
            print("hwnd", hwnd)

            # 打印窗口样式，判断是否有系统边框
            GWL_STYLE = -16
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            print(f"style=0x{style & 0xFFFFFFFF:08X}  WS_CAPTION={'Y' if style & 0x00C00000 else 'N'}")

            for pref, name in ((DWMWCP_ROUND, "ROUND"), (DWMWCP_ROUNDSMALL, "ROUNDSMALL")):
                rc = set_corner(hwnd, pref)
                print(f"DwmSetWindowAttribute({name}) -> {rc}")
                time.sleep(1.2)
                from PIL import ImageGrab

                r = wt.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
                out = ROOT / "tests" / f"probe_corner_{name.lower()}.png"
                ImageGrab.grab(bbox=(r.left - 20, r.top - 20, r.right + 20, r.bottom + 20)).save(out)
                print("saved", out)
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
