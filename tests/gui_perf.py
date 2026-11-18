"""性能基线：在真实 WebView2 里量一遍列表渲染的成本。

不测「感觉」，只测可复现的数字：
  · 100 条数据时一次 render 多少毫秒；
  · 连续添加 / 勾选 / 切筛选各要多少毫秒；
  · FLIP 是不是在「读一行布局→写一行样式」地来回逼浏览器重排。

用法：venv/Scripts/python.exe tests/gui_perf.py
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-perf-")

import webview  # noqa: E402

import app as appmod  # noqa: E402

BENCH = r"""
(function(){
  var A = window.__todoApp;
  var out = {};
  var items = [];
  for (var i = 0; i < 100; i++) {
    items.push({id:'p'+i, title:'性能任务 '+i, priority:'medium',
                due:'', done:false, createdAt:1000-i});
  }

  // 一次性建 100 条
  A.todos = A.normalizeTodos(items);
  var t0 = performance.now();
  A.render();
  out.render100 = Math.round((performance.now()-t0)*100)/100;

  // 切筛选 10 次（每次都会全量重建 + 读取布局）
  t0 = performance.now();
  for (var k=0;k<10;k++) {
    document.querySelector('.chip[data-filter="pending"]').click();
    document.querySelector('.chip[data-filter="all"]').click();
  }
  out.filter20 = Math.round((performance.now()-t0)*100)/100;

  // 勾选 20 条（每次 render 一遍）
  t0 = performance.now();
  for (var j=0;j<20;j++) A.toggle(A.todos[j].id);
  out.toggle20 = Math.round((performance.now()-t0)*100)/100;

  // 添加 20 条
  t0 = performance.now();
  for (var m=0;m<20;m++) {
    document.getElementById('inputText').value = '批量添加 '+m;
    document.getElementById('addBtn').click();
  }
  out.add20 = Math.round((performance.now()-t0)*100)/100;

  out.nodes = document.querySelectorAll('.todo-item').length;
  out.listeners = 0;  // 浏览器不暴露，靠代码结构判断
  return JSON.stringify(out);
})()
"""

# 对照：把 save_todos 换成空函数，分离「写盘/桥接」与「重渲染」各自的开销
BENCH_NO_SAVE = r"""
(function(){
  var api = window.pywebview.api;
  var orig = api.save_todos;
  api.save_todos = function(){ return Promise.resolve(true); };
  var A = window.__todoApp;
  var t0 = performance.now();
  for (var j=0;j<20;j++) A.toggle(A.todos[j].id);
  var toggle20 = Math.round((performance.now()-t0)*100)/100;
  t0 = performance.now();
  for (var m=0;m<20;m++) {
    document.getElementById('inputText').value = '无保存添加 '+m;
    document.getElementById('addBtn').click();
  }
  var add20 = Math.round((performance.now()-t0)*100)/100;
  api.save_todos = orig;
  return JSON.stringify({toggle20:toggle20, add20:add20});
})()
"""


def main() -> None:
    state = appmod.load_state()
    state["snap"] = False
    state["auto_collapse"] = False
    state["collapse_min"] = False

    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "perf", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window

    def runner() -> None:
        result = {}
        try:
            time.sleep(2.6)
            result = json.loads(window.evaluate_js(BENCH))
            result["noSave"] = json.loads(window.evaluate_js(BENCH_NO_SAVE))
        except Exception as exc:
            result = {"error": repr(exc)[:400]}
        finally:
            Path(__file__).resolve().parent.joinpath("gui_perf_result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.stdout.flush()
            os._exit(0)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
