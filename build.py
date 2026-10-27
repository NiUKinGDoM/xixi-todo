"""PyInstaller 打包：产出安装包的 payload（不直接发布）。

用 --onedir 而不是 --onefile：
- onefile 每次启动都要把 12MB 解压到临时目录，任务管理器里会看到
  两个同名进程（外层引导器 + 内层真身），用户会以为程序开了两份
- onedir 只有一个进程，启动也快得多
- 反正我们只发安装包，多出来的依赖文件都在安装目录里，用户看不到

用法：
    .venv\\Scripts\\python.exe build.py
产物：
    build\\payload\\xixi-todo\\（目录，供安装包打包，不进仓库）
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD_NAME = "xixi-todo"
PAYLOAD_DIR = ROOT / "build" / "payload"
ENTRY = ROOT / "app.py"
UI_DIR = ROOT / "ui"
ICON = UI_DIR / "app.ico"


def main() -> int:
    if not ICON.exists():
        print("图标缺失，先执行: python make_icon.py")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        PAYLOAD_NAME,
        "--icon",
        str(ICON),
        "--distpath",
        str(PAYLOAD_DIR),
        "--workpath",
        str(ROOT / "build"),
        "--specpath",
        str(ROOT / "build"),
        # ui 目录随包分发
        "--add-data",
        f"{UI_DIR}{';'}ui",
        # pywebview 依赖收集
        "--hidden-import",
        "webview.platforms.edgechromium",
        "--hidden-import",
        "webview.platforms.winforms",
        "--hidden-import",
        "clr",
        "--collect-submodules",
        "webview",
        str(ENTRY),
    ]

    print("执行:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("打包失败")
        return result.returncode

    app_dir = PAYLOAD_DIR / PAYLOAD_NAME
    exe = app_dir / f"{PAYLOAD_NAME}.exe"
    if exe.exists():
        total = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file())
        print(f"\npayload：{app_dir}  (exe {exe.stat().st_size/1024/1024:.1f} MB，"
              f"整目录 {total/1024/1024:.1f} MB)")
        print("下一步：python build_installer.py（生成 dist 下的安装包）")
    else:
        print("\n未找到产物")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
