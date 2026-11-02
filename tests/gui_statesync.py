"""开关连点与更新包复用：两处「状态不同步」类问题的回归测试。

  · 连点同一个开关两次，应该回到原状态（乐观更新，不能只生效一次）；
  · 安装包已经下好时再打开更新框，不应该让人重新下一次。

用法：venv/Scripts/python.exe tests/gui_statesync.py
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-sync-")

import webview  # noqa: E402

import app as appmod  # noqa: E402


def main() -> None:
    state = appmod.load_state()
    state["snap"] = True
    state["auto_collapse"] = False
    state["collapse_min"] = True
    state["on_top"] = True
    state["close_action"] = "quit"

    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "sync", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window
    result: dict = {}

    def runner() -> None:
        time.sleep(2.6)
        window.evaluate_js("document.getElementById('btnSettingsMini').click()")
        time.sleep(0.6)

        def click_twice(switch_id: str) -> dict:
            return json.loads(window.evaluate_js("""
              (function(){
                var n=document.getElementById('%s');
                n.click(); n.click();
                return JSON.stringify({cls:n.classList.contains('is-on')});
              })()
            """ % switch_id))

        for sid in ("setSnap", "setTop"):
            before = json.loads(api.get_window_state())
            click_twice(sid)
            time.sleep(1.0)
            after = json.loads(api.get_window_state())
            key = "snap" if sid == "setSnap" else "on_top"
            view = json.loads(window.evaluate_js(
                "JSON.stringify(document.getElementById('%s').classList.contains('is-on'))" % sid))
            result[sid] = {
                "before": before[key], "after": after[key], "view": view,
                "ok": before[key] == after[key] == view,
            }

        # 更新包复用：伪造一个「已下载完成」的状态，再打开更新框
        api._dl.update(state="done", path=sys.executable, total=12 * 1024 * 1024,
                       received=12 * 1024 * 1024)
        window.evaluate_js("""
          document.getElementById('setBack').click();
          window.__todoApp.openUpdateDialog({version:'9.9.9', notes:'回归测试', downloads:null});
        """)
        time.sleep(1.0)
        result["updateReuse"] = json.loads(window.evaluate_js("""
          (function(){
            return JSON.stringify({
              ok: document.getElementById('updOk').textContent,
              hint: document.getElementById('updHint').textContent,
              pct: document.getElementById('updPct').textContent
            });
          })()
        """))

        out = Path(__file__).resolve().parent / "gui_statesync_result.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.stdout.flush()
        os._exit(0)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
