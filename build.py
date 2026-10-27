"""PyInstaller 打包配置：生成单个 exe。

用法：
    .venv\\Scripts\\python.exe build.py
产物：
    dist\\xixiの待办清单.exe
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "xixiの待办清单"
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
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--icon",
        str(ICON),
        "--distpath",
        str(ROOT / "dist"),
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

    exe = ROOT / "dist" / f"{APP_NAME}.exe"
    if exe.exists():
        # 额外输出一份 ASCII 文件名：镜像/更新链接里中文路径容易被处理坏，
        # 用英文别名保证下载链接稳定可追踪。
        alias = ROOT / "dist" / "xixi-todo.exe"
        try:
            shutil.copy2(exe, alias)
        except Exception as exc:
            print(f"警告：未能生成英文别名 - {exc}")

        size_mb = exe.stat().st_size / 1024 / 1024
        print(f"\n完成：{exe}  ({size_mb:.1f} MB)")
        print(f"别名：{alias}")
    else:
        print("\n未找到产物")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
