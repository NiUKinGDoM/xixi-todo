"""开机自动检查更新：应用起来后不用点任何东西，自己就会去查。

判定不看结果（取决于当时有没有新版本、网络通不通），
只看「有没有真的发起过一次检查」：
  - 抓到了 checking=true（检查中），或
  - 抓到了 latest（已经有结果了）
任一条命中就说明自动检查跑过了。
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-auto-")

import webview  # noqa: E402
import app as appmod  # noqa: E402

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
        "auto", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    def runner():
        time.sleep(2.5)
        win = webview.windows[0]
        win.resize(380, 560)
        time.sleep(0.5)

        started = None
        latest = None
        deadline = time.time() + 14
        while time.time() < deadline:
            raw = win.evaluate_js(
                "JSON.stringify({c:window.__todoApp.getUpdateState().checking,"
                "l:window.__todoApp.getUpdateState().latest||''})"
            )
            st = json.loads(raw)
            if st["c"] and started is None:
                started = time.time()
            if st["l"]:
                latest = st["l"]
                break
            time.sleep(0.2)

        check("不点任何按钮就发起了检查", started is not None or latest is not None,
              f"checking_seen={started is not None} latest={latest}")
        check("检查能拿到版本号（网络或缓存任一可用）", latest is not None, f"latest={latest}")

        # 检查结束后不能一直卡在转圈
        time.sleep(0.8)
        stuck = win.evaluate_js(
            "document.getElementById('menuUpdate').classList.contains('is-checking')"
        )
        check("自动检查结束后不留转圈状态", stuck is False, str(stuck))

        ok = all(RESULTS)
        print(f"通过 {sum(RESULTS)} / {len(RESULTS)}", flush=True)
        os._exit(0 if ok else 2)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
