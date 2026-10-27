"""应用内更新面板：真实点开、真实下载、进度条真的走。

不点「立即安装」——那会真的拉起安装程序覆盖当前安装。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-updui-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def main() -> None:
    state = appmod.load_state()
    state.update({"mode": "mini", "snap": False, "auto_collapse": False})
    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "updui", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    dl = {
        "ghfast": "https://ghfast.top/https://github.com/NiUKinGDoM/xixi-todo/releases/latest/download/xixi-todo-setup.exe",
        "ghproxy": "https://gh-proxy.com/https://github.com/NiUKinGDoM/xixi-todo/releases/latest/download/xixi-todo-setup.exe",
        "github": "https://github.com/NiUKinGDoM/xixi-todo/releases/latest/download/xixi-todo-setup.exe",
    }

    def runner() -> None:
        time.sleep(3)
        win = webview.windows[0]
        win.resize(380, 560)
        time.sleep(0.6)

        # 打开面板（用假版本号，避免依赖线上到底发到第几版）
        win.evaluate_js(
            "window.__todoApp.openUpdateDialog(%s)" % json.dumps({
                "version": "9.9.9", "notes": "内测说明文字", "downloads": dl,
            })
        )
        time.sleep(0.6)
        check("更新面板已弹出",
              win.evaluate_js("!document.getElementById('updMask').hidden") is True)
        check("标题显示新版本",
              "9.9.9" in str(win.evaluate_js("document.getElementById('updTitle').textContent")))
        check("顶栏被收起",
              win.evaluate_js("getComputedStyle(document.querySelector('.minibar')).display") == "none")

        # 点「立即更新」开始下载
        win.evaluate_js("document.getElementById('updOk').click()")
        time.sleep(1.2)
        check("进度条出现",
              win.evaluate_js("!document.getElementById('updBar').hidden") is True)

        seen = []
        deadline = time.time() + 260
        state_done = False
        while time.time() < deadline:
            txt = win.evaluate_js(
                "JSON.stringify({p:document.getElementById('updPct').textContent,"
                "ok:document.getElementById('updOk').textContent,"
                "hint:document.getElementById('updHint').textContent})"
            )
            info = json.loads(txt)
            if info["p"] not in seen:
                seen.append(info["p"])
            if info["ok"] == "立即安装":
                state_done = True
                break
            if "失败" in info["hint"]:
                check("下载未失败", False, info["hint"])
                break
            time.sleep(0.8)

        check("进度有推进", len(seen) >= 3, f"看到 {len(seen)} 个进度值: {seen[:8]}")
        check("最终到达下载完成", state_done,
              win.evaluate_js("document.getElementById('updHint').textContent") or "")
        check("按钮变成立即安装",
              win.evaluate_js("document.getElementById('updOk').textContent") == "立即安装")

        prog = json.loads(api.get_download_progress())
        check("后端确认下载完成", prog["state"] == "done", str(prog.get("state")))
        check("文件已就位", Path(prog.get("path") or "").exists())

        # 取消/关闭面板，顺手清掉 14MB
        win.evaluate_js("document.getElementById('updCancel').click()")
        time.sleep(0.4)
        check("面板可关闭",
              win.evaluate_js("document.getElementById('updMask').hidden") is True)
        check("关闭后顶栏恢复",
              win.evaluate_js("getComputedStyle(document.querySelector('.minibar')).display") != "none")

        try:
            if prog.get("path"):
                os.remove(prog["path"])
        except Exception:
            pass

        ok = all(r[1] for r in RESULTS)
        print(f"通过 {sum(1 for r in RESULTS if r[1])} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
