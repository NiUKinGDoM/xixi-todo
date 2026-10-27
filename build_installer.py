"""生成 Windows 安装包（Inno Setup）。

用法：
    .venv\\Scripts\\python.exe build_installer.py

前置：先跑 build.py 打出 dist\\xixi-todo.exe，并且已安装 Inno Setup 6。
产物：dist\\xixiの待办清单-安装包.exe（唯一的发布物）

设计取舍：
- 按用户安装（{localappdata}\\Programs\\XiXiTodo），不弹 UAC，装完立刻能用
- 卸载信息写进 HKCU，控制面板「应用和功能」里能看到
- 开机自启动用 HKCU\\...\\Run 的 XiXiTodo 值，和应用内开关共用同一个键，
  不会出现「安装时开了、设置里关不掉」的双份配置
- 用户数据在 %APPDATA%\\xixi-todo，卸载不删，重装后待办还在
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
INSTALLER_DIR = ROOT / "installer"
APP_SRC_DIR = ROOT / "build" / "payload" / "xixi-todo"
APP_SRC = APP_SRC_DIR / "xixi-todo.exe"
ICON = ROOT / "ui" / "app.ico"
VERSION_JSON = ROOT / "version.json"

ISCC_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]

APP_DISPLAY_NAME = "xixiの待办"
SETUP_BASENAME = "xixiの待办清单-安装包"
APP_ID_GUID = "{{B4E1F0A2-7C3D-4A6E-9F21-3D5A8C2B7E10}"

ISS_TEMPLATE = r"""
; 由 build_installer.py 生成，不要手改
[Setup]
AppId={app_id}
AppName={app_name}
AppVersion={version}
AppVerName={app_name} {version}
AppPublisher={app_name}
AppPublisherURL=https://github.com/NiUKinGDoM/xixi-todo
AppSupportURL=https://github.com/NiUKinGDoM/xixi-todo
DefaultDirName={{localappdata}}\Programs\XiXiTodo
DefaultGroupName={app_name}
DisableProgramGroupPage=yes
DisableDirPage=auto
AllowNoIcons=yes
PrivilegesRequired=lowest
OutputDir={out_dir}
OutputBaseFilename={setup_name}
SetupIconFile={icon}
UninstallDisplayIcon={{app}}\xixi-todo.exe
UninstallDisplayName={app_name}
VersionInfoVersion={vi_version}
VersionInfoDescription={app_name} 安装程序
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=xixi-todo.exe
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "cn"; MessagesFile: "{lang_file}"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce
Name: "autostart"; Description: "开机自动启动（打开即是待办小卡片）"; GroupDescription: "启动："; Flags: checkedonce

[Files]
Source: "{app_src}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{autoprograms}}\{app_name}"; Filename: "{{app}}\xixi-todo.exe"; Comment: "桌面待办小卡片"
Name: "{{autodesktop}}\{app_name}"; Filename: "{{app}}\xixi-todo.exe"; Comment: "桌面待办小卡片"; Tasks: desktopicon

[Registry]
; 和应用内「开机自启动」开关是同一个值，谁都能关掉对方
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "XiXiTodo"; ValueData: {q3}{{app}}\xixi-todo.exe{q3}; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{{app}}\xixi-todo.exe"; Description: "打开 {app_name}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{{app}}"
"""


def find_iscc() -> Path | None:
    for p in ISCC_CANDIDATES:
        try:
            if p and p.exists():
                return p
        except OSError:
            continue
    return None


def read_version() -> str:
    try:
        data = json.loads(VERSION_JSON.read_text("utf-8"))
        v = str(data.get("version") or "").strip()
        if v:
            return v
    except Exception:
        pass
    # 退回读 app.py 里的 VERSION
    for line in (ROOT / "app.py").read_text("utf-8").splitlines():
        if line.startswith("VERSION"):
            return line.split("=", 1)[1].strip().strip('"\'')
    return "0.0.0"


def main() -> int:
    if not APP_SRC.exists():
        print("缺少 build/payload/xixi-todo/xixi-todo.exe，请先执行: python build.py")
        return 1
    if not ICON.exists():
        print("缺少 ui/app.ico")
        return 1

    iscc = find_iscc()
    if iscc is None:
        print("找不到 ISCC.exe（Inno Setup 6）。安装方式：winget install JRSoftware.InnoSetup")
        return 1

    version = read_version()
    vi_version = version if version.count(".") == 3 else version + ".0"

    lang_file = INSTALLER_DIR / "ChineseSimplified.isl"
    if not lang_file.exists():
        print("缺少 installer/ChineseSimplified.isl（中文安装界面语言包）")
        return 1

    iss = INSTALLER_DIR / "setup.iss"
    content = ISS_TEMPLATE.format(
        app_id=APP_ID_GUID,
        app_name=APP_DISPLAY_NAME,
        version=version,
        vi_version=vi_version,
        out_dir=DIST,
        setup_name=SETUP_BASENAME,
        icon=ICON,
        app_src=APP_SRC_DIR,
        lang_file=lang_file,
        q3='"""',
    )
    # Inno 6 支持 UTF-8 BOM，中文路径与文案都靠它
    iss.write_text(content.lstrip("\n"), encoding="utf-8-sig")
    print(f"生成脚本: {iss}")

    result = subprocess.run([str(iscc), str(iss)], cwd=str(ROOT))
    if result.returncode != 0:
        print("编译安装包失败")
        return result.returncode

    out = DIST / f"{SETUP_BASENAME}.exe"
    if out.exists():
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"\n完成：{out}  ({size_mb:.1f} MB)")
        return 0
    print("未找到安装包产物")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
