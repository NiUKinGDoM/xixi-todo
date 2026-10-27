"""系统托盘图标（纯 ctypes，无第三方依赖）。

为什么不用 pystray：只为了一个图标引入新依赖，打包体积和不确定性都上去了。
这里直接调 Shell_NotifyIconW，隐藏窗口收回调，自己跑消息循环。

线程约束：托盘在自己的线程里跑 GetMessage 循环，只调用 user32 的
ShowWindow / PostMessage，不碰 pywebview 的 .NET 对象 —— 之前踩过在非 UI 线程
调用 WinForms 成员导致 Invoke 死锁的坑，这里必须绕开。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
from pathlib import Path

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

# 独立的 user32 实例：下面要给 DefWindowProcW 定签名，
# 直接改 ctypes.windll.user32 会波及 pywebview 自己的调用（它的
# SetWindowPos 习惯传 None），一设 argtypes 就当场 ArgumentError。
# 默认签名下 LPARAM 被推断成 c_int，64 位指针一进来就 OverflowError，
# 结果托盘菜单的回调直接失效。
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_u32.DefWindowProcW.restype = ctypes.c_ssize_t
_u32.CallWindowProcW.argtypes = [ctypes.c_void_p, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_u32.CallWindowProcW.restype = ctypes.c_ssize_t

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY = 0x0080
TPM_RETURNCMD = 0x0100
SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9

ID_SHOW = 1001
ID_QUIT = 1002


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", wt.HICON),
        ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256),
        ("uTimeout", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64),
        ("dwInfoFlags", wt.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wt.HICON),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class TrayIcon:
    """一个托盘图标：左键单击/双击显示窗口，右键菜单显示/退出。"""

    def __init__(self, icon_path: Path, tip: str, on_show, on_quit) -> None:
        self.icon_path = str(icon_path)
        self.tip = tip[:127]
        self.on_show = on_show
        self.on_quit = on_quit
        self.hwnd = 0
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._wndproc_ref = None  # 防止回调被回收
        self._hicon = 0
        self._visible = False

    # ---------- 对外 ----------

    def start(self, timeout: float = 2.0) -> bool:
        """在后台线程创建图标，返回是否成功。"""
        if self._thread and self._thread.is_alive():
            return True
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return bool(self.hwnd)

    def hide(self) -> None:
        if self.hwnd and self._visible:
            data = self._data()
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
            self._visible = False

    def stop(self) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    # ---------- 内部 ----------

    def _data(self) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_TRAY
        data.hIcon = self._hicon
        data.szTip = self.tip
        return data

    def _run(self) -> None:
        try:
            hinst = kernel32.GetModuleHandleW(None)
            cls = f"XiXiTodoTray_{id(self)}"
            self._wndproc_ref = WNDPROC(self._wnd_proc)
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wndproc_ref
            wc.hInstance = hinst
            wc.lpszClassName = cls
            if not user32.RegisterClassW(ctypes.byref(wc)):
                return
            # 隐藏窗口：只为收托盘回调消息
            self.hwnd = user32.CreateWindowExW(
                0, cls, "XiXiTodoTray", 0, 0, 0, 0, 0, None, None, hinst, None
            )
            if not self.hwnd:
                return

            self._hicon = user32.LoadImageW(
                None, self.icon_path, IMAGE_ICON, 0, 0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
            data = self._data()
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
                return
            self._visible = True
        finally:
            self._ready.set()

        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._safe(self.on_show)
            elif event == WM_RBUTTONUP:
                self._menu()
            return 0
        if msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == ID_SHOW:
                self._safe(self.on_show)
            elif cmd == ID_QUIT:
                self._safe(self.on_quit)
            return 0
        if msg == WM_CLOSE:
            self.hide()
            user32.DestroyWindow(hwnd)
            user32.PostQuitMessage(0)
            return 0
        if msg == WM_DESTROY:
            return 0
        return _u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        user32.AppendMenuW(menu, MF_STRING, ID_SHOW, "显示待办")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "退出应用")
        # 必须先把隐藏窗口设为前台，否则点别处菜单不会消失
        user32.SetForegroundWindow(self.hwnd)
        pos = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pos))
        cmd = user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_NONOTIFY | TPM_RETURNCMD,
            pos.x, pos.y, 0, self.hwnd, None,
        )
        user32.PostMessageW(self.hwnd, 0, 0, 0)
        user32.DestroyMenu(menu)
        if cmd:
            self._wnd_proc(self.hwnd, WM_COMMAND, cmd, 0)

    @staticmethod
    def _safe(fn) -> None:
        try:
            fn()
        except Exception:
            pass
