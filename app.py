"""
xixiの待办清单 · Liquid Glass 桌面应用
=====================================
宿主层：pywebview (Edge WebView2 / Chromium 内核)
数据层：%APPDATA%\\xixi-todo\\todos.json
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from pathlib import Path

import webview

from tray import SW_HIDE, SW_SHOW, TrayIcon

APP_NAME = "xixiの待办清单"
APP_ID = "xixi-todo"
OLD_APP_ID = "TodoGlass"          # 改名前的数据目录，用于自动迁移
VERSION = "1.5.0"
REPO = "NiUKinGDoM/xixi-todo"

# 界面上显示的短名，用户可在菜单里改（小卡片标题 / 侧边栏 / 窗口标题共用）
DEFAULT_APP_NAME = "xixiの待办"

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------


def _resource_dir() -> Path:
    """定位 ui 资源目录（兼容 PyInstaller 单文件模式）。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base / "ui"


def _data_dir() -> Path:
    # 允许用环境变量指定数据目录（测试用临时目录隔离，避免污染真实数据；
    # 也可以把程序和配置放在同一文件夹里做绿色版）
    override = os.environ.get("XIXI_TODO_DATA_DIR")
    if override:
        d = Path(override)
        d.mkdir(parents=True, exist_ok=True)
        return d

    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    _migrate_old_data(Path(base) / OLD_APP_ID, d)
    return d


def _migrate_old_data(old: Path, new: Path) -> None:
    """软件改过名字，把旧目录的数据搬过来一次。

    只在「旧目录有数据、新目录还没有」时执行，避免覆盖用户后来的修改。
    """
    try:
        if not old.is_dir():
            return
        marker = new / ".migrated"
        if marker.exists():
            return

        copied = 0
        for name in ("todos.json", "groups.json", "window.json"):
            src = old / name
            dst = new / name
            if src.exists() and not dst.exists():
                dst.write_bytes(src.read_bytes())
                copied += 1

        if copied:
            _log(f"migrated {copied} file(s) from {old.name} to {new.name}")
        marker.touch()
    except Exception as exc:
        _log(f"migrate failed: {exc}")


DATA_FILE = _data_dir() / "todos.json"
NOTIFIED_FILE = _data_dir() / "notified.json"
STATE_FILE = _data_dir() / "window.json"
LOG_FILE = _data_dir() / "app.log"

# 窗口尺寸（迷你桌面卡片 / 完整视图）
MINI_W, MINI_H = 380, 560
FULL_W, FULL_H = 1080, 720
MINI_MIN = (300, 400)

# 迷你卡片的几档尺寸：(宽, 高, 名称)
MINI_PRESETS = [
    (320, 470, "紧凑"),
    (380, 560, "标准"),
    (460, 660, "宽大"),
]

# 拖动窗口后距离屏幕边缘多少像素内自动吸附
EDGE_SNAP_PX = 30

# 收进屏幕边缘时的小条尺寸（薄边 × 长边）
COLLAPSE_THIN, COLLAPSE_LONG = 20, 104

# 开机自启动：写 HKCU 的 Run 键，和安装包共用同一个值名，
# 这样「安装时勾选」和「设置里打开」不会互相打架。
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# 值名允许被环境变量覆盖：自动化测试要用真实注册表路径验证开关，
# 但绝不能碰用户真正的启动项，所以挂一个测试专用名字。
AUTOSTART_NAME = os.environ.get("XIXI_TODO_REG_NAME") or "XiXiTodo"


def _log(msg: str) -> None:
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {msg}\n")
    except Exception:
        pass


# --------------------------------------------------------------------------
# 数据存储
# --------------------------------------------------------------------------


class JsonList:
    """通用 JSON 数组存取，带原子写入与损坏备份。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> list:
        with self._lock:
            if not self.path.exists():
                return []
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception as exc:
                _log(f"load {self.path.name} failed: {exc}")
                try:
                    self.path.rename(self.path.with_suffix(".json.corrupt"))
                except Exception:
                    pass
                return []

    def save(self, items: list) -> bool:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            try:
                tmp.write_text(
                    json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                tmp.replace(self.path)
                return True
            except Exception as exc:
                _log(f"save {self.path.name} failed: {exc}")
                return False


class Store(JsonList):
    """待办数据。"""


# --------------------------------------------------------------------------
# 窗口状态（模式 / 置顶 / 位置尺寸）
# --------------------------------------------------------------------------

DEFAULT_STATE = {
    "mode": "mini",
    "on_top": True,
    "snap": True,
    "app_name": DEFAULT_APP_NAME,
    "mini_preset": 1,
    "collapsed": False,
    "collapse_edge": "",
    "collapse_min": True,
    "auto_collapse": True,
    "close_action": "quit",
    "mini": {"x": None, "y": None, "w": MINI_W, "h": MINI_H},
    "full": {"x": None, "y": None, "w": FULL_W, "h": FULL_H},
}


def load_state() -> dict:
    state = {
        "mode": DEFAULT_STATE["mode"],
        "on_top": DEFAULT_STATE["on_top"],
        "snap": DEFAULT_STATE["snap"],
        "app_name": DEFAULT_STATE["app_name"],
        "mini_preset": DEFAULT_STATE["mini_preset"],
        "collapsed": False,
        "collapse_edge": "",
        "collapse_min": True,
        "auto_collapse": True,
        "close_action": "quit",
        "mini": dict(DEFAULT_STATE["mini"]),
        "full": dict(DEFAULT_STATE["full"]),
    }
    # 收起是临时状态：上次退出时如果是贴边小条（甚至被强杀），
    # 这次冷启动必须正常打开，不能一开机就是一条 20px 的缝。
    state["collapsed"] = False
    state["collapse_edge"] = ""

    try:
        if STATE_FILE.exists():
            raw = json.loads(STATE_FILE.read_text("utf-8"))
            if isinstance(raw, dict):
                if raw.get("mode") in ("mini", "full"):
                    state["mode"] = raw["mode"]
                if isinstance(raw.get("on_top"), bool):
                    state["on_top"] = raw["on_top"]
                if isinstance(raw.get("collapse_min"), bool):
                    state["collapse_min"] = raw["collapse_min"]
                if isinstance(raw.get("auto_collapse"), bool):
                    state["auto_collapse"] = raw["auto_collapse"]
                if raw.get("close_action") in ("quit", "tray"):
                    state["close_action"] = raw["close_action"]
                if isinstance(raw.get("snap"), bool):
                    state["snap"] = raw["snap"]
                if isinstance(raw.get("app_name"), str) and raw["app_name"].strip():
                    state["app_name"] = raw["app_name"].strip()[:16]
                try:
                    idx = int(raw.get("mini_preset", 1))
                    # -1 表示「用户自由缩放过、不匹配任何档位」
                    if -1 <= idx < len(MINI_PRESETS):
                        state["mini_preset"] = idx
                except Exception:
                    pass
                for k in ("mini", "full"):
                    if isinstance(raw.get(k), dict):
                        state[k].update({kk: vv for kk, vv in raw[k].items() if vv is not None})
    except Exception as exc:
        _log(f"load state failed: {exc}")
    return state


def save_state(state: dict) -> None:
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(STATE_FILE)
    except Exception as exc:
        _log(f"save state failed: {exc}")


def _launch_command() -> str:
    """写进注册表的启动命令。打包后就是 exe 本身；开发态用 pythonw 跑 app.py。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    runner = pyw if pyw.exists() else Path(sys.executable)
    entry = Path(__file__).resolve().parent / "app.py"
    return f'"{runner}" "{entry}"'


def is_autostart_enabled() -> bool:
    """读注册表判断是否已设置开机自启动。"""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            value, _type = winreg.QueryValueEx(key, AUTOSTART_NAME)
        return bool(str(value).strip())
    except Exception:
        return False


def write_autostart(enabled: bool) -> bool:
    """开启 / 关闭开机自启动。返回写入后的真实状态。"""
    # 测试用临时数据目录时不要动真实注册表
    if os.environ.get("XIXI_TODO_DATA_DIR") and not os.environ.get("XIXI_TODO_ALLOW_REG"):
        return is_autostart_enabled()
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, AUTOSTART_NAME, 0, winreg.REG_SZ, _launch_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        _log(f"autostart -> {bool(enabled)}")
        return bool(enabled)
    except Exception as exc:
        _log(f"set autostart failed: {exc}")
        return is_autostart_enabled()


def clamp_to_screen(x: int, y: int, w: int, h: int, margin: int = 8) -> tuple[int, int]:
    """把窗口位置收进屏幕可见范围。

    从右下角的小卡片切到 1080x720 的完整视图时，按原位置展开会有一半跑到屏幕外，
    所以每次切换都要按新尺寸重新钳制。
    """
    try:
        scr = webview.screens[0]
        sw, sh = int(scr.width), int(scr.height)
        sx, sy = int(scr.x), int(scr.y)
    except Exception:
        return x, y

    # 窗口比屏幕还大时，贴左上角
    max_x = sx + sw - w - margin
    max_y = sy + sh - h - margin
    if max_x < sx + margin:
        max_x = sx + margin
    if max_y < sy + margin:
        max_y = sy + margin

    x = max(sx + margin, min(int(x), max_x))
    y = max(sy + margin, min(int(y), max_y))
    return x, y


def centered_position(w: int, h: int) -> tuple[int, int]:
    try:
        scr = webview.screens[0]
        return (
            int(scr.x + (scr.width - w) // 2),
            int(scr.y + (scr.height - h) // 2),
        )
    except Exception:
        return 100, 100


# --------------------------------------------------------------------------
# 窗口形状 / 贴边 / 尺寸（Win32）
# --------------------------------------------------------------------------
# 说明：pywebview 的 transparent=True 在 WebView2 上并没有真正让窗口透明，
# 窗口底色仍是不透明的浅灰，导致「卡片四周有一圈白边」。
# 这里改用 SetWindowRgn 直接把窗口裁成圆角，卡片铺满窗口，白边彻底消失。

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi

# Windows 11 原生圆角（DWM 绘制，带抗锯齿与系统投影）
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_ROUND = 2
# 圆角处系统会画一条 1px 边线，默认中灰偏重；换成与玻璃相称的浅色。
# COLORREF 是 0x00BBGGRR 顺序：#E2E7F5
DWM_BORDER_COLOR = (245 << 16) | (231 << 8) | 226


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


_EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def _find_hwnd_by_title(title: str) -> int:
    hits: list[int] = []

    def _cb(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n == 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value == title:
                hits.append(hwnd)
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(_EnumProc(_cb), 0)
    except Exception:
        pass
    return hits[0] if hits else 0


def _hwnd_of(win) -> int:
    """尽量拿到窗口句柄：优先用 pywebview 的原生句柄，失败则按标题查找。"""
    try:
        native = getattr(win, "native", None)
        if native is not None and hasattr(native, "Handle"):
            return int(native.Handle.ToInt32())
    except Exception:
        pass
    try:
        return _find_hwnd_by_title(win.title)
    except Exception:
        return 0


def _screen_for(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    """窗口落在哪块屏幕上（返回该屏幕的 x, y, width, height）。

    pywebview.screens[0] 永远是主屏，副屏上贴边会算错、收起来还会跳回主屏。
    """
    best = None
    best_area = -1
    try:
        for scr in webview.screens:
            sx, sy = int(scr.x), int(scr.y)
            sw, sh = int(scr.width), int(scr.height)
            ox = max(0, min(x + w, sx + sw) - max(x, sx))
            oy = max(0, min(y + h, sy + sh) - max(y, sy))
            area = ox * oy
            if area > best_area:
                best_area = area
                best = (sx, sy, sw, sh)
    except Exception as exc:
        _log(f"screen lookup failed: {exc}")
    if best is None:
        try:
            scr = webview.screens[0]
            best = (int(scr.x), int(scr.y), int(scr.width), int(scr.height))
        except Exception:
            best = (0, 0, 1920, 1080)
    return best


def _window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = _RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def apply_round_region(win, radius: int = 22) -> bool:
    """把窗口裁成圆角矩形。成功返回 True。

    SetWindowRgn 之后系统接管区域对象，不再需要（也不能）DeleteObject。

    注意：窗口区域是二值遮罩，没有抗锯齿，22px 圆角用它会看出一格格的阶梯。
    所以正常情况下走 shape_window() 的 DWM 路径，这里只作为系统不支持时的兜底。
    """
    hwnd = _hwnd_of(win)
    if not hwnd:
        return False
    try:
        _x, _y, w, h = _window_rect(hwnd)
        if w <= 0 or h <= 0:
            return False
        rgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius * 2, radius * 2)
        if not rgn:
            return False
        user32.SetWindowRgn(hwnd, rgn, True)
        return True
    except Exception as exc:
        _log(f"round region failed: {exc}")
        return False


def shape_window(win, radius: int = 22) -> str:
    """把窗口做成圆角卡片，返回实际使用的方式（dwm / region / none）。

    优先用 Windows 11 的 DWM 圆角：由系统合成器绘制，边缘抗锯齿、带投影。
    老系统或调用失败时才退回 SetWindowRgn（会有锯齿，但至少是圆角）。
    """
    hwnd = _hwnd_of(win)
    if not hwnd:
        return "none"

    # 先清掉历史区域，避免和 DWM 圆角叠加出双重裁切
    try:
        user32.SetWindowRgn(hwnd, None, True)
    except Exception:
        pass

    try:
        val = ctypes.c_int(DWMWCP_ROUND)
        rc = dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(val), ctypes.sizeof(val)
        )
        if rc == 0:
            # 顺手把边线调淡，避免圆角处出现一道突兀的灰色发丝线
            try:
                bcol = ctypes.c_uint(DWM_BORDER_COLOR)
                dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_BORDER_COLOR, ctypes.byref(bcol), ctypes.sizeof(bcol)
                )
            except Exception:
                pass
            return "dwm"
        _log(f"DwmSetWindowAttribute rc={rc}, fallback to region")
    except Exception as exc:
        _log(f"dwm round failed: {exc}")

    return "region" if apply_round_region(win, radius) else "none"


# --------------------------------------------------------------------------
# 纯 Win32 窗口控制
# --------------------------------------------------------------------------
# 教训（血泪）：pywebview 的 Window.on_top / set_title / minimize / destroy
# 最终都会碰 WinForms 对象。而 js_api 回调运行在一个**新建的工作线程**上，
# 此时 UI 线程正卡在 threading.Thread.start() 里等新线程就绪，无法处理
# 跨线程 Invoke / 窗口消息 —— 两边互等，整个界面永久卡死。
#
# 实测调用栈（点一下置顶就死）：
#   js_api 线程 → window.on_top setter → winforms.set_on_top → i.TopMost
#   主线程     → js_bridge_call → Thread.start() → _started.wait()
#
# 所以：凡是 js_api 里要动的窗口属性，一律走 user32，不碰 pywebview 的
# Python 属性，也不碰 .NET。
# --------------------------------------------------------------------------

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SW_MINIMIZE = 6
SW_SHOW = 5
SW_HIDE = 0
SW_RESTORE = 9
WM_CLOSE = 0x0010

# 注意：绝不能在 ctypes.windll.user32 上设 argtypes。
# pywebview 自己的 winforms 后端也用同一个 DLL 对象调 SetWindowPos，
# 它习惯传 None 表示「不改这一项」；一旦被我们钉死成 c_int，它当场抛
# ArgumentError，窗口 move / resize 全线失效。
# 所以这里开一个独立的 WinDLL 实例，只给本文件这几个函数用。
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_u32.SetWindowPos.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
]
_u32.SetWindowPos.restype = ctypes.c_bool
_u32.SetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
_u32.SetWindowTextW.restype = ctypes.c_bool
_u32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
_u32.ShowWindow.restype = ctypes.c_bool
_u32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
_u32.PostMessageW.restype = ctypes.c_bool
_u32.SetForegroundWindow.argtypes = [ctypes.c_void_p]


def win_set_topmost(hwnd: int, on_top: bool) -> bool:
    """置顶 / 取消置顶（不改 Z 序以外的东西）。"""
    if not hwnd:
        return False
    try:
        after = HWND_TOPMOST if on_top else HWND_NOTOPMOST
        ok = _u32.SetWindowPos(
            ctypes.c_void_p(hwnd), ctypes.c_void_p(after),
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
        _log(f"topmost -> {on_top} ok={bool(ok)}")
        return bool(ok)
    except Exception as exc:
        _log(f"set topmost failed: {exc}")
        return False


def win_set_title(hwnd: int, title: str) -> bool:
    if not hwnd:
        return False
    try:
        return bool(_u32.SetWindowTextW(ctypes.c_void_p(hwnd), title))
    except Exception as exc:
        _log(f"set title failed: {exc}")
        return False


def win_minimize(hwnd: int) -> bool:
    if not hwnd:
        return False
    try:
        return bool(_u32.ShowWindow(ctypes.c_void_p(hwnd), SW_MINIMIZE))
    except Exception as exc:
        _log(f"minimize failed: {exc}")
        return False


def win_show(hwnd: int, restore: bool = True) -> bool:
    """从托盘 / 最小化恢复。"""
    if not hwnd:
        return False
    try:
        _u32.ShowWindow(ctypes.c_void_p(hwnd), SW_RESTORE if restore else SW_SHOW)
        _u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        return True
    except Exception as exc:
        _log(f"show failed: {exc}")
        return False


def win_request_close(hwnd: int) -> bool:
    """异步请求关窗。

    用 PostMessage 而不是 win.destroy()：后者是同步 Invoke，
    在 js_api 线程里会把界面顶死；PostMessage 只是投递消息，立即返回。
    """
    if not hwnd:
        return False
    try:
        return bool(_u32.PostMessageW(ctypes.c_void_p(hwnd), WM_CLOSE, None, None))
    except Exception as exc:
        _log(f"request close failed: {exc}")
        return False


def snap_window_to_edge(win, enabled: bool = True) -> tuple[int, int] | None:
    """靠近屏幕边缘时自动吸附。返回吸附后的坐标，未吸附返回 None。"""
    if not enabled:
        return None
    hwnd = _hwnd_of(win)
    if not hwnd:
        return None
    try:
        x, y, w, h = _window_rect(hwnd)
        scr = webview.screens[0]
        sx, sy = int(scr.x), int(scr.y)
        sw, sh = int(scr.width), int(scr.height)

        nx, ny = x, y
        if abs(x - sx) <= EDGE_SNAP_PX:
            nx = sx
        elif abs((sx + sw) - (x + w)) <= EDGE_SNAP_PX:
            nx = sx + sw - w
        if abs(y - sy) <= EDGE_SNAP_PX:
            ny = sy
        elif abs((sy + sh) - (y + h)) <= EDGE_SNAP_PX:
            ny = sy + sh - h

        if (nx, ny) != (x, y):
            win.move(nx, ny)
            return nx, ny
        return None
    except Exception as exc:
        _log(f"snap failed: {exc}")
        return None


# --------------------------------------------------------------------------
# 单实例锁（避免双开导致数据互相覆盖）
# --------------------------------------------------------------------------

_lock_handle = None


def acquire_single_instance_lock() -> bool:
    """尝试取得单实例锁。

    放在函数里而不是模块顶层：这样测试代码 import app 时不会被锁挡住，
    只有真正启动应用（main）才加锁。
    返回 False 表示已有实例在运行。
    """
    global _lock_handle
    try:
        import msvcrt

        lock_file = _data_dir() / "app.lock"
        _lock_handle = open(lock_file, "a+b")
        try:
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    except Exception:
        _lock_handle = None
        return True  # 非 Windows 或不支持时放行


# --------------------------------------------------------------------------
# JS API（暴露给前端）
# --------------------------------------------------------------------------


class Api:
    def __init__(
        self,
        store: Store,
        window_holder: dict,
        state: dict | None = None,
    ) -> None:
        self.store = store
        self.window_holder = window_holder
        self.state = state if state is not None else load_state()
        # 前端拖动期间为 True，用来抑制自动贴边
        self._dragging = False
        # 程序化改几何（展开/换尺寸/切模式）后的冷却截止时间。
        # 这些操作也会触发 moved 事件，不拦的话刚展开就被吸回屏幕边。
        self._suppress_snap_until = 0.0
        self._tray = None
        # 启动后的静默期：on_shown 的 resize/move 也会触发 moved，
        # 不拦的话应用一启动就吸到边、又自动收成小条。
        self._quiet_until = 0.0
        # 只有用户真的拖动过，才做「贴边自动收起」；
        # 程序自己挪窗口（切模式、展开）不算。
        self._user_dragged = False

    # ---------- 数据 ----------

    def load_todos(self) -> str:
        """返回 JSON 字符串。前端通过 pywebview.api.load_todos() 调用。"""
        return json.dumps(self.store.load(), ensure_ascii=False)

    def save_todos(self, payload: str) -> bool:
        """保存待办列表。payload 为 JSON 字符串。"""
        try:
            items = json.loads(payload)
        except Exception as exc:
            _log(f"save_todos parse failed: {exc}")
            return False
        if not isinstance(items, list):
            return False
        return self.store.save(items)

    def notify(self, title: str, message: str) -> bool:
        """触发一条系统通知（用于到期提醒）。"""
        return _send_toast(title, message)

    # ---------- 版本 / 更新 ----------

    def get_version(self) -> str:
        return VERSION

    def open_url(self, url: str) -> bool:
        """用系统默认浏览器打开链接。

        WebView2 里 window.open 行为不可控，统一交给 Python 唤浏览器更可靠。
        """
        url = str(url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return False
        try:
            import webbrowser

            webbrowser.open(url)
            _log(f"open url: {url}")
            return True
        except Exception as exc:
            _log(f"open_url failed: {exc}")
            return False

    # ---------- 备份 ----------

    def export_backup(self, payload: str) -> str:
        """弹出保存对话框，把 payload 写入用户选择的位置。返回文件路径或空串。"""
        win = self._win()
        if win is None:
            return ""
        try:
            default_name = "待办备份-" + time.strftime("%Y%m%d-%H%M") + ".json"
            result = win.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=default_name,
                file_types=("JSON 备份 (*.json)",),
            )
            if not result:
                return ""
            target = result[0] if isinstance(result, (list, tuple)) else result
            Path(target).write_text(payload, encoding="utf-8")
            _log(f"backup exported to {target}")
            return str(target)
        except Exception as exc:
            _log(f"export_backup failed: {exc}")
            return ""

    def import_backup(self) -> str:
        """弹出打开对话框，读取备份文件内容。返回文件内容字符串或空串。"""
        win = self._win()
        if win is None:
            return ""
        try:
            result = win.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=("JSON 备份 (*.json)", "所有文件 (*.*)"),
            )
            if not result:
                return ""
            target = result[0] if isinstance(result, (list, tuple)) else result
            text = Path(target).read_text(encoding="utf-8")
            _log(f"backup imported from {target}")
            return text
        except Exception as exc:
            _log(f"import_backup failed: {exc}")
            return ""

    # ---------- 窗口 ----------

    def _win(self):
        return self.window_holder.get("window")

    def _snapshot(self, mode: str) -> None:
        """把当前窗口位置（迷你模式还含尺寸）记到指定模式下。

        收起状态下窗口是贴边的小条，尺寸不代表卡片，必须跳过，
        否则退出时会把 20x104 记成卡片尺寸。
        """
        if self.state.get("collapsed"):
            return
        win = self._win()
        if win is None:
            return
        try:
            slot = self.state.setdefault(mode, {})
            slot["x"] = int(win.x)
            slot["y"] = int(win.y)
            if mode == "mini":
                hwnd = _hwnd_of(win)
                if hwnd:
                    _x, _y, w, h = _window_rect(hwnd)
                    if w > 0 and h > 0:
                        slot["w"] = w
                        slot["h"] = h
        except Exception as exc:
            _log(f"snapshot failed: {exc}")

    def get_window_state(self) -> str:
        return json.dumps(
            {
                "mode": self.state.get("mode", "mini"),
                "on_top": bool(self.state.get("on_top", True)),
                "snap": bool(self.state.get("snap", True)),
                "app_name": self.state.get("app_name") or DEFAULT_APP_NAME,
                "mini_preset": int(self.state.get("mini_preset", 1)),
                "collapsed": bool(self.state.get("collapsed", False)),
                "collapse_edge": self.state.get("collapse_edge", ""),
                "collapse_min": bool(self.state.get("collapse_min", True)),
                "auto_collapse": bool(self.state.get("auto_collapse", True)),
                "close_action": self.state.get("close_action", "quit"),
                "autostart": is_autostart_enabled(),
            },
            ensure_ascii=False,
        )

    # ---------- 应用名 ----------

    def set_app_name(self, name: str) -> str:
        """重命名应用。同时更新窗口标题，前端会同步小卡片与侧边栏。"""
        name = str(name or "").strip()[:16]
        if not name:
            return self.get_window_state()
        self.state["app_name"] = name
        win = self._win()
        # SetWindowTextW 是纯 user32，不会引发跨线程 Invoke 死锁
        win_set_title(_hwnd_of(win) if win is not None else 0, name)
        save_state(self.state)
        return self.get_window_state()

    # ---------- 贴边 / 尺寸 ----------

    def set_snap(self, enabled) -> str:
        self.state["snap"] = bool(enabled)
        save_state(self.state)
        return self.get_window_state()

    def set_collapse_min(self, enabled) -> str:
        """开关：最小化时是否收进屏幕边缘。"""
        self.state["collapse_min"] = bool(enabled)
        save_state(self.state)
        return self.get_window_state()

    def set_close_action(self, action) -> str:
        """关闭按钮的行为：quit = 退出应用，tray = 收进托盘。"""
        value = str(action or "").strip()
        if value in ("quit", "tray"):
            self.state["close_action"] = value
            save_state(self.state)
        return self.get_window_state()

    def set_auto_collapse(self, enabled) -> str:
        """开关：拖到屏幕边缘松手后是否直接收进边缘。"""
        self.state["auto_collapse"] = bool(enabled)
        save_state(self.state)
        return self.get_window_state()

    def set_autostart(self, enabled) -> str:
        """开关：开机自启动（写 HKCU 的 Run 键，无需管理员权限）。"""
        write_autostart(bool(enabled))
        return self.get_window_state()

    def _mute_snap(self, seconds: float = 0.9) -> None:
        """接下来一小段时间内不做自动贴边。"""
        self._suppress_snap_until = time.monotonic() + seconds

    def set_dragging(self, flag) -> bool:
        if flag:
            self._user_dragged = True
        """前端拖动窗口期间置位：此时不做自动贴边。

        拖动是 JS 逐帧调 move 模拟的，拖动中停顿超过防抖时长会被误判成
        「拖完了」，窗口自己弹到边上。有这面旗子就能分清。
        """
        self._dragging = bool(flag)
        return self._dragging

    def snap_now(self) -> str:
        """拖动结束后调用：靠近屏幕边缘就吸上去。"""
        win = self._win()
        if win is None or self.state.get("collapsed"):
            return self.get_window_state()
        # 吸附本身会改坐标 → 触发 moved → 再排一次自动贴边判定。
        # 吸完先静默一小会儿，避免「吸附 → 判定 → 自动收起」连锁。
        self._mute_snap(0.5)
        result = snap_window_to_edge(win, bool(self.state.get("snap", True)))
        if result:
            _log(f"snapped to {result}")
        return self.get_window_state()

    def set_mini_preset(self, index) -> str:
        """切换迷你卡片尺寸档位。"""
        win = self._win()
        try:
            idx = int(index)
        except Exception:
            return self.get_window_state()
        if idx < 0 or idx >= len(MINI_PRESETS):
            return self.get_window_state()

        self.state["mini_preset"] = idx
        w, h, _name = MINI_PRESETS[idx]
        self.state.setdefault("mini", {})
        self.state["mini"]["w"] = w
        self.state["mini"]["h"] = h

        if win is not None and self.state.get("mode", "mini") == "mini":
            self._mute_snap()
            try:
                win.resize(w, h)
                tx, ty = clamp_to_screen(int(win.x), int(win.y), w, h)
                win.move(tx, ty)
            except Exception as exc:
                _log(f"set_mini_preset failed: {exc}")
            shape_window(win, 22)

        save_state(self.state)
        return self.get_window_state()

    # ---------- 自由缩放 ----------

    def resize_window(self, w, h) -> str:
        """拖动手柄时的实时改尺寸（高频调用，不落盘）。"""
        win = self._win()
        if win is None:
            return self.get_window_state()
        try:
            cw = max(MINI_MIN[0], min(int(w), 1200))
            ch = max(MINI_MIN[1], min(int(h), 1400))
            win.resize(cw, ch)
        except Exception as exc:
            _log(f"resize_window failed: {exc}")
        return ""

    def finish_resize(self) -> str:
        """松手后收尾：重新裁圆角、识别是否命中档位、落盘。"""
        win = self._win()
        if win is None:
            return self.get_window_state()
        try:
            _x, _y, w, h = _window_rect(_hwnd_of(win))
        except Exception:
            w, h = 0, 0

        if w > 0 and h > 0:
            idx = -1
            for i, (pw, ph, _n) in enumerate(MINI_PRESETS):
                if abs(w - pw) <= 4 and abs(h - ph) <= 4:
                    idx = i
                    break
            self.state["mini_preset"] = idx
            slot = self.state.setdefault("mini", {})
            slot["w"] = w
            slot["h"] = h
            # 缩放后可能顶出屏幕，拉回来
            try:
                tx, ty = clamp_to_screen(int(win.x), int(win.y), w, h)
                if (tx, ty) != (int(win.x), int(win.y)):
                    win.move(tx, ty)
                slot["x"], slot["y"] = tx, ty
            except Exception:
                pass

        shape_window(win, 22 if self.state.get("mode", "mini") == "mini" else 14)
        save_state(self.state)
        return self.get_window_state()

    def _mini_size(self) -> tuple[int, int]:
        """迷你模式当前应有的尺寸：命中档位用档位值，否则用记录的自定义值。"""
        idx = self.state.get("mini_preset", 1)
        slot = self.state.get("mini") or {}
        if isinstance(idx, int) and 0 <= idx < len(MINI_PRESETS):
            return MINI_PRESETS[idx][0], MINI_PRESETS[idx][1]
        try:
            w = int(slot.get("w") or MINI_PRESETS[1][0])
            h = int(slot.get("h") or MINI_PRESETS[1][1])
            return max(MINI_MIN[0], w), max(MINI_MIN[1], h)
        except Exception:
            return MINI_PRESETS[1][0], MINI_PRESETS[1][1]

    def apply_region(self) -> bool:
        """重新给窗口裁圆角（切换模式/尺寸后调用）。"""
        win = self._win()
        if win is None:
            return False
        radius = 22 if self.state.get("mode", "mini") == "mini" else 14
        return shape_window(win, radius)

    def set_mode(self, mode: str) -> str:
        """切换 迷你 / 完整 模式，返回新状态 JSON。"""
        win = self._win()
        if win is None or mode not in ("mini", "full"):
            return self.get_window_state()

        prev = self.state.get("mode", "mini")
        if prev == mode:
            return self.get_window_state()

        self._snapshot(prev)
        self.state["mode"] = mode

        if mode == "mini":
            w, h = self._mini_size()
        else:
            w, h = FULL_W, FULL_H

        try:
            win.resize(w, h)
        except Exception as exc:
            _log(f"resize failed: {exc}")

        # 目标模式有记录位置就用它，否则以当前窗口中心为准展开/收起，
        # 最后统一钳制到屏幕内，避免大窗口跑出屏幕。
        slot = self.state.get(mode, {})
        try:
            if slot.get("x") is not None and slot.get("y") is not None:
                tx, ty = int(slot["x"]), int(slot["y"])
            else:
                try:
                    if prev == "mini":
                        pw, ph = self._mini_size()
                    else:
                        pw, ph = FULL_W, FULL_H
                    cx = int(win.x) + pw // 2
                    cy = int(win.y) + ph // 2
                    tx, ty = cx - w // 2, cy - h // 2
                except Exception:
                    tx, ty = centered_position(w, h)

            tx, ty = clamp_to_screen(tx, ty, w, h)
            win.move(tx, ty)
            # 记录钳制后的实际位置，下次切换可直接复用
            self.state.setdefault(mode, {})
            self.state[mode]["x"], self.state[mode]["y"] = tx, ty
        except Exception as exc:
            _log(f"move failed: {exc}")

        # 尺寸变了要重新裁圆角，否则裁剪区域还是旧尺寸
        shape_window(win, 22 if mode == "mini" else 14)

        save_state(self.state)
        return self.get_window_state()

    def toggle_on_top(self) -> str:
        win = self._win()
        new_val = not bool(self.state.get("on_top", True))
        self.state["on_top"] = new_val
        # 绝不能写 win.on_top：js_api 线程碰 WinForms 属性会和 UI 线程互等死锁
        win_set_topmost(_hwnd_of(win) if win is not None else 0, new_val)
        save_state(self.state)
        return self.get_window_state()

    def minimize_window(self):
        """最小化。

        「最小化时收进边缘」开着（默认）时，不管窗口此刻在哪，都缩成贴边小条，
        再点一下还原。之前要求窗口正好贴着屏幕边才收，很多人点完没反应，
        以为功能坏了 —— 现在位置无关，点最小化必然缩小。
        关掉这个开关就退回系统最小化。
        """
        win = self._win()
        if win is None:
            return ""
        if bool(self.state.get("collapse_min", True)):
            edge = self._nearest_edge(win, limit=None)
            if edge:
                return self.collapse_window(edge)
        # win.minimize() 内部是同步 Invoke，js_api 线程里会死锁，改走 user32
        win_minimize(_hwnd_of(win))
        return ""

    # ---------- 收进屏幕边缘 ----------

    def _nearest_edge(self, win, limit: int | None = EDGE_SNAP_PX) -> str | None:
        """窗口离哪条屏幕边最近。

        limit=None 时不看距离，直接返回最近的一条边（最小化收边用）。
        """
        try:
            hwnd = _hwnd_of(win)
            if not hwnd:
                return None
            x, y, w, h = _window_rect(hwnd)
            sx, sy, sw, sh = _screen_for(x, y, w, h)
            gaps = {
                "left": abs(x - sx),
                "right": abs(sx + sw - (x + w)),
                "top": abs(y - sy),
                "bottom": abs(sy + sh - (y + h)),
            }
            edge = min(gaps, key=gaps.get)
            if limit is not None and gaps[edge] > limit:
                return None
            return edge
        except Exception as exc:
            _log(f"nearest edge failed: {exc}")
            return None

    def collapse_window(self, edge: str) -> str:
        win = self._win()
        if win is None or self.state.get("collapsed"):
            return self.get_window_state()

        try:
            hwnd = _hwnd_of(win)
            x, y, w, h = _window_rect(hwnd)
        except Exception:
            return self.get_window_state()

        # 记住展开时要回到哪儿（按当前模式存，完整视图要回到完整尺寸）
        mode = self.state.get("mode", "mini")
        slot = self.state.setdefault(mode, {})
        slot["x"], slot["y"], slot["w"], slot["h"] = x, y, w, h

        if edge in ("left", "right"):
            nw, nh = COLLAPSE_THIN, COLLAPSE_LONG
        else:
            nw, nh = COLLAPSE_LONG, COLLAPSE_THIN

        sx, sy, sw, sh = _screen_for(x, y, w, h)

        if edge == "left":
            nx = sx
            ny = y + h // 2 - nh // 2
        elif edge == "right":
            nx = sx + sw - nw
            ny = y + h // 2 - nh // 2
        elif edge == "top":
            ny = sy
            nx = x + w // 2 - nw // 2
        else:  # bottom
            ny = sy + sh - nh
            nx = x + w // 2 - nw // 2

        # margin=0：收进边缘就要贴死在边上，不能留 8px 缝
        nx, ny = clamp_to_screen(nx, ny, nw, nh, margin=0)

        self.state["collapsed"] = True
        self.state["collapse_edge"] = edge

        try:
            win.resize(nw, nh)
        except Exception as exc:
            _log(f"collapse resize failed: {exc}")
        try:
            win.move(nx, ny)
        except Exception as exc:
            _log(f"collapse move failed: {exc}")
        shape_window(win, 10)

        save_state(self.state)
        _log(f"collapsed to {edge} ({nx},{ny} {nw}x{nh})")
        return self.get_window_state()

    def expand_window(self) -> str:
        win = self._win()
        if win is None or not self.state.get("collapsed"):
            return self.get_window_state()

        mode = self.state.get("mode", "mini")
        slot = self.state.get(mode) or {}
        if mode == "full":
            fallback_w, fallback_h = FULL_W, FULL_H
        else:
            fallback_w, fallback_h = MINI_PRESETS[self.state.get("mini_preset", 1)][:2]
        w = int(slot.get("w") or fallback_w)
        h = int(slot.get("h") or fallback_h)
        self._mute_snap(1.1)

        self.state["collapsed"] = False
        self.state["collapse_edge"] = ""

        try:
            win.resize(w, h)
        except Exception as exc:
            _log(f"expand resize failed: {exc}")
        try:
            x = int(slot.get("x")) if slot.get("x") is not None else int(win.x)
            y = int(slot.get("y")) if slot.get("y") is not None else int(win.y)
            tx, ty = clamp_to_screen(x, y, w, h)
            win.move(tx, ty)
        except Exception as exc:
            _log(f"expand move failed: {exc}")
        shape_window(win, 22 if mode == "mini" else 14)

        save_state(self.state)
        _log(f"expanded from edge ({w}x{h})")
        return self.get_window_state()

    def close_window(self) -> None:
        self._snapshot(self.state.get("mode", "mini"))
        save_state(self.state)
        if self.state.get("close_action", "quit") == "tray" and self._hide_to_tray():
            return
        self.quit_app()

    # ---------- 托盘 ----------

    def _tray_show(self) -> None:
        """从托盘恢复窗口。只调 user32，不碰 .NET 对象。"""
        win = self._win()
        hwnd = _hwnd_of(win) if win is not None else 0
        if not hwnd:
            return
        win_show(hwnd)

    def _ensure_tray(self) -> bool:
        if self._tray is not None:
            return True
        icon = _resource_dir() / "app.ico"
        if not icon.exists():
            _log("tray icon missing")
            return False
        self._tray = TrayIcon(
            icon,
            self.state.get("app_name") or DEFAULT_APP_NAME,
            on_show=self._tray_show,
            on_quit=self.quit_app,
        )
        ok = self._tray.start()
        if not ok:
            self._tray = None
        _log(f"tray start -> {ok}")
        return ok

    def _hide_to_tray(self) -> bool:
        if not self._ensure_tray():
            return False
        win = self._win()
        hwnd = _hwnd_of(win) if win is not None else 0
        if not hwnd:
            return False
        _u32.ShowWindow(ctypes.c_void_p(hwnd), SW_HIDE)
        _log("hide to tray")
        return True

    def quit_app(self) -> None:
        """真正退出（托盘菜单与关闭按钮共用）。"""
        tray = self._tray
        self._tray = None
        if tray is not None:
            try:
                tray.stop()
            except Exception as exc:
                _log(f"tray stop failed: {exc}")
        win = self._win()
        if win is not None:
            # 先投递 WM_CLOSE 让 pywebview 走正常关闭流程（会落盘、退出消息循环）
            if win_request_close(_hwnd_of(win)):
                return
            try:
                win.destroy()
            except Exception as exc:
                _log(f"destroy failed: {exc}")


# --------------------------------------------------------------------------
# 系统通知（Windows Toast，无需额外依赖）
# --------------------------------------------------------------------------


def _send_toast(title: str, message: str) -> bool:
    """通过 Windows Runtime 发送 Toast 通知，无需第三方依赖。"""
    try:
        import subprocess

        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, "
            "Windows.UI.Notifications, ContentType=WindowsRuntime] > $null\n"
            "$t=[Windows.UI.Notifications.ToastNotificationManager]::"
            "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)\n"
            "$n=$t.GetElementsByTagName('text')\n"
            "$n.Item(0).AppendChild($t.CreateTextNode(" + ps_quote(title) + ")) > $null\n"
            "$n.Item(1).AppendChild($t.CreateTextNode(" + ps_quote(message) + ")) > $null\n"
            "[Windows.UI.Notifications.ToastNotificationManager]::"
            "CreateToastNotifier(" + ps_quote(APP_NAME) + ").Show("
            "[Windows.UI.Notifications.ToastNotification]::new($t))\n"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            timeout=10,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception as exc:
        _log(f"toast failed: {exc}")
        return False


def ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


# --------------------------------------------------------------------------
# 到期提醒调度
# --------------------------------------------------------------------------


def _hm_to_minutes(hm: str) -> int | None:
    try:
        h, m = hm.split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return None


def collect_reminders(
    items: list,
    today: str,
    now_hm: str,
    notified: set[str],
    grace_minutes: int = 360,
) -> list[tuple[str, str, str, bool]]:
    """纯函数：算出「这一刻应该处理哪些提醒」。

    返回 [(去重键, 通知标题, 通知内容, 是否弹窗)]。
    抽成纯函数是为了能脱离线程直接单测。

    规则：
      - 已完成的跳过
      - 日期早于今天 → 逾期提醒，每天一次
      - 日期等于今天且设了时间 → 到点提醒；超过宽限期（默认 6 小时）
        只记录不弹窗，避免晚上打开应用时被一堆陈旧提醒轰炸
      - 日期等于今天但没设时间 → 当天提醒一次
    去重键包含 due 与 time，因此重复任务滚到下一次后会自动重新提醒。
    """
    out: list[tuple[str, str, str, bool]] = []
    now_min = _hm_to_minutes(now_hm) or 0

    for t in items:
        if not isinstance(t, dict) or t.get("done"):
            continue
        due = t.get("due") or ""
        if not due:
            continue
        tid = str(t.get("id", ""))
        title = str(t.get("title", ""))[:60]
        when = t.get("time") or ""

        if due < today:
            key = f"{tid}|{due}|overdue"
            if key not in notified:
                out.append((key, "待办已逾期", title, True))
        elif due == today:
            if when:
                when_min = _hm_to_minutes(when)
                if when_min is None:
                    continue
                if now_min >= when_min:
                    key = f"{tid}|{due}|{when}"
                    if key not in notified:
                        late = now_min - when_min
                        out.append((key, f"待办提醒 {when}", title, late <= grace_minutes))
            else:
                key = f"{tid}|{due}|day"
                if key not in notified:
                    out.append((key, "今天到期", title, True))
    return out


def _reminder_loop(api: Api, stop: threading.Event) -> None:
    """每 30 秒检查一次到期任务，已提醒记录持久化，避免重启后重复打扰。"""
    notified_store = JsonList(NOTIFIED_FILE)
    notified: set[str] = set(str(x) for x in notified_store.load() if isinstance(x, str))
    _log(f"reminder loop start, notified={len(notified)}")

    while not stop.wait(30):
        try:
            items = api.store.load()
            today = time.strftime("%Y-%m-%d")
            now_hm = time.strftime("%H:%M")

            due_list = collect_reminders(items, today, now_hm, notified)
            if not due_list:
                continue

            for key, title, message, show in due_list:
                notified.add(key)
                if show:
                    _send_toast(title, message)
                else:
                    _log(f"stale reminder skipped: {key}")

            # 清理 45 天前的记录并落盘，顺便限制总量
            cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - 45 * 86400))
            kept = set()
            for k in notified:
                parts = k.split("|")
                if len(parts) >= 2 and parts[1] >= cutoff:
                    kept.add(k)
            notified = kept
            notified_store.save(sorted(notified)[-2000:])
        except Exception as exc:
            _log(f"reminder loop error: {exc}")


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def main() -> None:
    if not acquire_single_instance_lock():
        print("程序已在运行，请勿重复启动。")
        sys.exit(0)

    ui_dir = _resource_dir()
    index = ui_dir / "index.html"
    if not index.exists():
        print(f"找不到界面文件: {index}")
        sys.exit(1)

    store = Store(DATA_FILE)
    state = load_state()
    holder: dict = {}
    api = Api(store, holder, state)

    # 必须传普通文件路径（而非 file:// URI）：
    # pywebview 的 is_local_url() 对 file:// 返回 False，
    # 本地静态服务器不会启动，而 JS API 桥接正是走该服务器的
    # /js_api/{uid} POST 路由 —— 用 file:// 会导致数据无法持久化。
    url = str(index)
    _log(f"loading {url}")

    mode = state.get("mode", "mini")
    preset_idx = state.get("mini_preset", 1)
    if isinstance(preset_idx, int) and 0 <= preset_idx < len(MINI_PRESETS):
        preset_w, preset_h = MINI_PRESETS[preset_idx][0], MINI_PRESETS[preset_idx][1]
    else:
        # -1：用户自由缩放过，用记录的自定义尺寸
        _mini_slot = state.get("mini") or {}
        preset_w = int(_mini_slot.get("w") or MINI_PRESETS[1][0])
        preset_h = int(_mini_slot.get("h") or MINI_PRESETS[1][1])
    width = preset_w if mode == "mini" else FULL_W
    height = preset_h if mode == "mini" else FULL_H
    app_title = state.get("app_name") or DEFAULT_APP_NAME

    window = webview.create_window(
        app_title,
        url=url,
        js_api=api,
        width=width,
        height=height,
        # 故意不设 min_size：收起成 20px 小条时，
        # 把 WinForms 的 MinimumSize 调大/调小会触发跨线程 Invoke，
        # 而 js_api 回调本身在非 UI 线程，会直接死锁。
        # 最小尺寸由 resize_window / 前端手柄自己钳制。
        min_size=(1, 1),
        # 无边框 + 透明：窗口本身不画背景，圆角与阴影全部由页面绘制，
        # 这样迷你卡片才能真正像浮在桌面上的一块玻璃。
        frameless=True,
        # easy_drag 绝对不能再开：它会往 window 上挂一个全局 mousedown，
        # 窗口里任何位置按下鼠标都开始拖窗口。后果是——
        # 点按钮时手抖两像素，窗口先被拖走，click 目标丢失，按钮「点不动」；
        # 拖拽排序、框选文字、拖右下角缩放也全被抢。
        # 标题栏拖动由 .pywebview-drag-region 单独负责，不依赖 easy_drag。
        easy_drag=False,
        # transparent 在 WebView2 上并不真正生效（窗口底色仍是不透明浅灰，
        # 会露出一圈白边），所以关掉它。
        transparent=False,
        # shadow=True 会让 pywebview 走 DWM 渲染策略（NCRENDERING=ENABLED），
        # 这是 Windows 11 原生圆角生效的前提，同时带回系统投影。
        shadow=True,
        on_top=bool(state.get("on_top", True)),
        text_select=True,
        confirm_close=False,
    )
    holder["window"] = window

    def on_shown() -> None:
        """首次显示时校正尺寸并按上次记录定位。

        pywebview 在 Windows 上先按“带边框”的尺寸设置窗口，之后才切换为无边框，
        导致客户区少掉一圈边框厚度（实测 380x560 会变成 364x521）。
        所以显示后再按目标尺寸 resize 一次，把尺寸拉回设计值。
        """
        _log(f"on_shown: mode={mode} target={width}x{height} collapsed={state.get('collapsed')}")
        try:
            window.resize(width, height)
        except Exception as exc:
            _log(f"initial resize failed: {exc}")

        # 先把圆角裁好再定位，避免先闪一下方角
        shape_window(window, 22 if mode == "mini" else 14)

        try:
            slot_state = state.get(mode, {})
            if slot_state.get("x") is not None and slot_state.get("y") is not None:
                tx, ty = int(slot_state["x"]), int(slot_state["y"])
            else:
                # 默认贴右下角，任务栏上方留出空间
                scr = webview.screens[0]
                margin = 28
                tx = scr.width - width - margin
                ty = scr.height - height - margin - 60
            tx, ty = clamp_to_screen(tx, ty, width, height)
            window.move(tx, ty)
        except Exception as exc:
            _log(f"initial position failed: {exc}")

        # 尺寸与位置都定下来后再裁一次，确保圆角与最终几何匹配
        shape_window(window, 22 if mode == "mini" else 14)
        # 启动阶段别吸附、别自动收起
        api._quiet_until = time.monotonic() + 2.0

    # ---- 拖动结束后自动贴边 ----
    # pywebview 的 moved 事件会在拖动过程中持续触发，没法区分「正在拖」和「拖完了」。
    # 用防抖：每次移动重置一个 0.45s 的定时器，定时器到期才算拖动结束，此时再吸附。
    snap_timer: dict = {"t": None}
    snap_busy = {"v": False}

    def _do_auto_snap() -> None:
        if snap_busy["v"] or not state.get("snap", True) or getattr(api, "_dragging", False):
            return
        if time.monotonic() < getattr(api, "_suppress_snap_until", 0.0):
            return
        if time.monotonic() < getattr(api, "_quiet_until", 0.0):
            return
        win = holder.get("window")
        if win is None:
            return
        snap_busy["v"] = True
        try:
            moved_to = snap_window_to_edge(win, True)
            if moved_to:
                _log(f"auto snap -> {moved_to}")
                api._snapshot(state.get("mode", "mini"))
                save_state(state)
                # 贴到边就收进边缘，不用再点一次最小化
                if (state.get("auto_collapse", True)
                        and getattr(api, "_user_dragged", False)
                        and not state.get("collapsed")):
                    api._mute_snap(1.0)
                    api.collapse_window(api._nearest_edge(win, limit=None))
        except Exception as exc:
            _log(f"auto snap failed: {exc}")
        finally:
            snap_busy["v"] = False

    def on_moved(_x, _y) -> None:
        if state.get("collapsed") or not state.get("snap", True) or snap_busy["v"]:
            return
        old = snap_timer.get("t")
        if old is not None:
            try:
                old.cancel()
            except Exception:
                pass
        timer = threading.Timer(0.45, _do_auto_snap)
        timer.daemon = True
        snap_timer["t"] = timer
        timer.start()

    def on_closing() -> None:
        timer = snap_timer.get("t")
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
        api._snapshot(state.get("mode", "mini"))
        save_state(state)

    try:
        window.events.shown += on_shown
        window.events.moved += on_moved
        window.events.closing += on_closing
    except Exception as exc:
        _log(f"event hook failed: {exc}")

    stop = threading.Event()
    t = threading.Thread(target=_reminder_loop, args=(api, stop), daemon=True)
    t.start()

    _log(f"app start v{VERSION}, mode={mode}, data={DATA_FILE}")

    try:
        webview.start(debug=False)
    finally:
        stop.set()
        _log("app exit")


if __name__ == "__main__":
    main()
