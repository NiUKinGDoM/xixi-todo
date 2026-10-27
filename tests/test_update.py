"""应用内更新：真实下载一次安装包，验证进度与完整性。

不测 install_update（它会真的拉起安装程序覆盖当前安装），
只验证「能不能下下来、进度对不对、文件是不是完整安装包」。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-upd-")

import app as appmod  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def main() -> None:
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), {}, appmod.load_state())

    check("初始状态是 idle", json.loads(api.get_download_progress())["state"] == "idle")

    urls = [
        "https://ghfast.top/https://github.com/NiUKinGDoM/xixi-todo/releases/latest/download/xixi-todo-setup.exe",
        "https://gh-proxy.com/https://github.com/NiUKinGDoM/xixi-todo/releases/latest/download/xixi-todo-setup.exe",
        "https://github.com/NiUKinGDoM/xixi-todo/releases/latest/download/xixi-todo-setup.exe",
    ]
    t0 = time.time()
    res = json.loads(api.download_update(json.dumps(urls)))
    check("下载已启动", res.get("ok") is True, str(res))

    deadline = time.time() + 180
    last_pct = -1
    grew = False
    while time.time() < deadline:
        st = json.loads(api.get_download_progress())
        if st["state"] == "done":
            break
        if st["state"] == "error":
            check("下载成功", False, st.get("error", ""))
            break
        if st["percent"] > last_pct:
            last_pct = st["percent"]
            grew = True
        time.sleep(0.5)

    st = json.loads(api.get_download_progress())
    cost = time.time() - t0
    check("下载完成", st["state"] == "done", f"state={st['state']} err={st.get('error')}")
    check("进度有过增长", grew, f"最后 {last_pct}%")
    check("百分比到 100", st.get("percent") == 100, str(st.get("percent")))

    path = st.get("path") or ""
    exists = bool(path) and Path(path).exists()
    size = Path(path).stat().st_size if exists else 0
    check("安装包已落盘", exists, path)
    check("文件大小像安装包", size > 10 * 1024 * 1024, f"{size/1024/1024:.1f} MB")
    check("下载耗时合理", cost < 180, f"{cost:.1f}s")

    # MZ 头 = Windows PE 可执行文件
    head = b""
    if exists:
        with open(path, "rb") as f:
            head = f.read(2)
    check("下到的是可执行文件", head == b"MZ", str(head))

    # 清掉临时安装包，别占着 14MB
    try:
        if exists:
            os.remove(path)
    except Exception:
        pass

    ok = all(r[1] for r in RESULTS)
    print(f"通过 {sum(1 for r in RESULTS if r[1])} / {len(RESULTS)}", flush=True)
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
