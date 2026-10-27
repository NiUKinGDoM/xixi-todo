"""开机自动查到的更新要能自动弹窗。

做法：把本地版本号伪造成 1.5.0，让「最新版」必然比本地新；
清掉「今天已经提醒过」的标记，再手动触发一次静默检查，
断言：查到新版本 → 弹窗自动出现 → 标题带新版本号。
顺带验证 Releases API 这一路能把版本号带回来（反代有缓存时它是唯一可靠的源）。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-prompt-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

appmod.VERSION = "1.5.0"  # 只要比远端小，就一定判定为「有新版本」

RESULTS: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def main() -> None:
    state = appmod.load_state()
    state.update({"mode": "mini", "snap": False, "auto_collapse": False})
    holder = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "prompt", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    def runner():
        time.sleep(2.5)
        win = webview.windows[0]
        win.resize(380, 560)
        time.sleep(0.5)

        # 清掉「同一个版本今天提醒过」的标记，保证这次会弹
        win.evaluate_js("try{localStorage.removeItem('updatePrompted');}catch(e){}")
        win.evaluate_js("window.__todoApp.getUpdateState().checking=false;"
                        "window.__todoApp.getUpdateState().task=null;")
        win.evaluate_js("window.__todoApp.checkUpdate(true)")  # 模拟开机那次静默检查

        deadline = time.time() + 15
        latest = ""
        while time.time() < deadline:
            time.sleep(0.4)
            st = json.loads(win.evaluate_js(
                "JSON.stringify({c:window.__todoApp.getUpdateState().checking,"
                "l:window.__todoApp.getUpdateState().latest||''})"
            ))
            if not st["c"] and st["l"]:
                latest = st["l"]
                break

        check("查到了远端版本号（含 API 兜底那一路）", bool(latest), f"latest={latest}")
        check("远端版本比本地新", bool(latest) and latest != "1.5.0", f"{latest} vs 1.5.0")

        time.sleep(0.6)
        shown = win.evaluate_js("!document.getElementById('updMask').hidden")
        title = win.evaluate_js("document.getElementById('updTitle').textContent")
        check("自动弹出更新框", shown is True, f"shown={shown}")
        check("弹窗标题带新版本号", bool(latest) and latest in (title or ""), f"title={title}")

        marked = win.evaluate_js("localStorage.getItem('updatePrompted') || ''")
        check("记下已提醒，避免同一天反复弹", bool(latest) and latest in (marked or ""),
              f"marked={marked}")

        ok = all(RESULTS)
        print(f"通过 {sum(RESULTS)} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
