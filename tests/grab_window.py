"""截取运行中 exe 的窗口画面，用于最终视觉验收。

用 Win32 GDI 的 PrintWindow 抓取目标窗口内容（即使被遮挡也能抓到真实渲染结果）。
"""

import ctypes
import ctypes.wintypes as wt
import sys
from pathlib import Path

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

PW_RENDERFULLCONTENT = 0x00000002
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0

WINDOW_TITLE_FILTER = "待办事项"


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]


EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

found: list[tuple[int, str]] = []


def _cb(hwnd, _lparam):
    if not user32.IsWindowVisible(hwnd):
        return True
    n = user32.GetWindowTextLengthW(hwnd)
    if n == 0:
        return True
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    title = buf.value
    if WINDOW_TITLE_FILTER in title:
        found.append((hwnd, title))
    return True


def save_png(pixels: bytes, width: int, height: int, path: Path) -> bool:
    """把 BGRA 像素写成 BMP（无需第三方库）。"""
    import struct

    row_size = width * 4
    pad = (4 - (row_size % 4)) % 4
    padded = row_size + pad
    # BMP 是自底向上存储
    rows = []
    for y in range(height - 1, -1, -1):
        start = y * row_size
        row = pixels[start:start + row_size]
        rows.append(row + b"\x00" * pad)
    data = b"".join(rows)

    file_header = struct.pack("<2sIHHI", b"BM", 14 + 40 + len(data), 0, 0, 54)
    info = struct.pack(
        "<IiiHHIIiiII",
        40, width, height, 1, 32, 0, len(data), 2835, 2835, 0, 0,
    )
    path.write_bytes(file_header + info + data)
    return True


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("window.bmp")

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    if not found:
        print("NO_WINDOW_FOUND")
        return 1

    hwnd, title = found[0]
    print(f"找到窗口: hwnd={hwnd} title={title!r}")

    # 前置
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    ctypes.windll.kernel32.Sleep(700)

    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w = r.right - r.left
    h = r.bottom - r.top
    print(f"窗口尺寸: {w}x{h}")

    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc_mem, hbmp)

    ok = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
    if not ok:
        ok = user32.PrintWindow(hwnd, hdc_mem, 0)
    print(f"PrintWindow 结果: {ok}")

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # 负值 = 自顶向下
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    lines = gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    print(f"GetDIBits 扫描行: {lines}")

    save_png(buf.raw, w, h, out)
    print(f"已保存: {out}")

    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
