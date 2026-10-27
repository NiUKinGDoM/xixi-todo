"""真实跑一遍应用内安装：确认不再弹「Windows 找不到 '\\' 文件」。

这个测试会真的执行一次静默安装（装的是同一个版本，幂等），
为的是端到端验证那条启动安装程序的命令。
判定标准有两条：
  1) 安装目录里的 unins000.dat 被重写（说明安装程序确实跑完了）
  2) 屏幕上没有出现标题为反斜杠的系统错误对话框
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-inst-")

import app as appmod  # noqa: E402

u32 = ctypes.windll.user32
SETUP = ROOT / "dist" / "xixiの待办清单-安装包.exe"
TARGET_DIR = Path(r"D:\XiXiTodo")
STAMP = TARGET_DIR / "unins000.dat"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def backslash_dialogs() -> list[str]:
    """枚举顶层窗口，找出标题只剩反斜杠的系统错误框。"""
    found: list[str] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(hwnd, _lparam):
        cls = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "#32770":
            return True
        n = u32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value.strip()
        if title and set(title) == {"\\"}:
            found.append(title)
        return True

    u32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def main() -> int:
    if not SETUP.exists():
        print(f"缺少安装包: {SETUP}")
        return 2
    before = STAMP.stat().st_mtime if STAMP.exists() else 0

    api = appmod.Api(appmod.Store(appmod.DATA_FILE), {})
    api._dl["path"] = str(SETUP)
    # 别让测试结束时真的去销毁窗口
    api.quit_app = lambda: None  # type: ignore[assignment]

    check("安装前没有残留错误框", not backslash_dialogs())
    started = api.install_update()
    check("发起安装", started is True, str(started))

    # 等安装程序跑完（2 秒延迟 + 解压 + 写入）
    deadline = time.time() + 60
    changed = False
    while time.time() < deadline:
        time.sleep(2)
        now = STAMP.stat().st_mtime if STAMP.exists() else 0
        if now and now != before:
            changed = True
            break

    check("安装程序确实执行完了", changed,
          f"{before} -> {STAMP.stat().st_mtime if STAMP.exists() else 'missing'}")
    dialogs = backslash_dialogs()
    check("没有弹出「Windows 找不到 '\\' 文件」", not dialogs, str(dialogs))

    ok = all(RESULTS)
    print(f"通过 {sum(RESULTS)} / {len(RESULTS)}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
