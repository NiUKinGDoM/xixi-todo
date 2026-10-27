"""PyInstaller 打包：产出安装包的 payload（不直接发布）。

应用只以安装包形式分发，所以这里只生成一个中间产物，
由 build_installer.py 打进 setup.exe。dist 里只留安装包，
避免用户误点「免安装版」。

用法：
    .venv\\Scripts\\python.exe build.py
产物：
    build\\payload\\xixi-todo.exe（供安装包打包，不进仓库）
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
        "--onefile",
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

    exe = PAYLOAD_DIR / f"{PAYLOAD_NAME}.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / 1024 / 1024
        print(f"\npayload：{exe}  ({size_mb:.1f} MB)")
        print("下一步：python build_installer.py（生成 dist 下的安装包）")
    else:
        print("\n未找到产物")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
