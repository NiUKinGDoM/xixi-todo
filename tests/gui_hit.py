"""真实命中测试：检查每个按钮在屏幕上是否真的点得到。

DOM 的 .click() 能绕过所有遮挡，所以「事件都绑定了、程序化点也没报错」
并不能说明用户点得动。这里用 elementFromPoint 检查按钮中心点实际命中谁，
把被覆盖层、渐隐遮罩、布局溢出错位的按钮找出来。

用法：venv/Scripts/python.exe tests/gui_hit.py
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-hit-")

import webview  # noqa: E402

import app as appmod  # noqa: E402

OUT = Path(__file__).resolve().parent / "gui_hit_result.json"

SCAN_JS = r"""
(function(){
  var out = [];
  var nodes = document.querySelectorAll('button, .switch, .seg-btn, [role="switch"]');
  for (var i = 0; i < nodes.length; i++) {
    var b = nodes[i];
    if (!b.getClientRects().length) continue;
    var st = getComputedStyle(b);
    if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.05) continue;
    var r = b.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    var x = r.left + r.width / 2, y = r.top + r.height / 2;
    var off = (x < 0 || y < 0 || x > innerWidth || y > innerHeight);
    var hit = off ? null : document.elementFromPoint(x, y);
    var reachable = !off && !!hit && (hit === b || b.contains(hit));
    out.push({
      id: b.id || (b.className || '').toString().slice(0, 40) || b.tagName,
      text: (b.textContent || '').trim().slice(0, 12),
      rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      offscreen: off,
      reachable: reachable,
      blocker: reachable ? '' : (hit ? ((hit.id || '') + '.' + (hit.className || '')).slice(0, 60) : 'null')
    });
  }
  return JSON.stringify({w: innerWidth, h: innerHeight, items: out});
})()
"""


def main() -> None:
    state = appmod.load_state()
    state["snap"] = False
    state["auto_collapse"] = False
    state["close_action"] = "quit"

    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "hit",
        url=str(ROOT / "ui" / "index.html"),
        js_api=api,
        width=380,
        height=560,
        min_size=(1, 1),
        frameless=True,
        easy_drag=False,
        transparent=False,
        shadow=True,
        on_top=True,
    )
    holder["window"] = window

    report: dict = {}

    def runner() -> None:
        time.sleep(2.5)
        report["mini"] = json.loads(window.evaluate_js(SCAN_JS))
        window.evaluate_js("document.getElementById('btnSettingsMini').click()")
        time.sleep(0.7)
        report["settings_mini"] = json.loads(window.evaluate_js(SCAN_JS))
        # 滚到底部，验证下半部分按钮真的能滚到、能点到
        window.evaluate_js(
            "var b=document.querySelector('.settings-body');"
            "b.scrollTop=b.scrollHeight;"
        )
        time.sleep(0.6)
        report["settings_mini_bottom"] = json.loads(window.evaluate_js(SCAN_JS))
        window.evaluate_js("document.getElementById('setBack').click()")
        time.sleep(0.5)
        window.evaluate_js("document.getElementById('btnMode').click()")
        time.sleep(1.2)
        report["full"] = json.loads(window.evaluate_js(SCAN_JS))
        window.evaluate_js("document.getElementById('btnSettings').click()")
        time.sleep(0.7)
        report["settings_full"] = json.loads(window.evaluate_js(SCAN_JS))

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        for scope, data in report.items():
            bad = [it for it in data["items"] if not it["reachable"]]
            print(f"\n== {scope}  {data['w']}x{data['h']}  可点 {len(data['items']) - len(bad)}/{len(data['items'])}")
            for it in bad:
                print(f"   ✗ {it['id']:22s} {it['rect']} blocker={it['blocker']} off={it['offscreen']}")
        os._exit(0)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
