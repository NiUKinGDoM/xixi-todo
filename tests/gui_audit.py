"""交互巡检：跑一遍真实窗口里的主要功能，收集 JS 异常、状态不一致、布局越界。

不追求像素级视觉判断，只回答三个问题：
  1. 有没有 JS 抛错（整段功能直接坏掉的那种）；
  2. 前端显示的开关状态和后端真实配置是否一致；
  3. 有没有元素跑出可视区、被遮挡、挤成 0 尺寸。

用法：venv/Scripts/python.exe tests/gui_audit.py
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-audit-")

import webview  # noqa: E402

import app as appmod  # noqa: E402

OUT = Path(__file__).resolve().parent / "gui_audit_result.json"

HOOK_JS = r"""
(function(){
  window.__errs = [];
  window.addEventListener('error', function (e) {
    window.__errs.push(String(e.message) + ' @' + (e.filename || '').split('/').pop() + ':' + e.lineno);
  });
  window.addEventListener('unhandledrejection', function (e) {
    window.__errs.push('promise: ' + String(e.reason));
  });
  return 'ok';
})()
"""

TAIL_JS = r"""
(function(){
  var errs = window.__errs || [];
  window.__errs = [];
  return JSON.stringify(errs);
})()
"""

LAYOUT_JS = r"""
(function(){
  var out = [];
  var vw = innerWidth, vh = innerHeight;
  var nodes = document.querySelectorAll(
    '.todo-item, .mini-foot, .hero, .composer, .progress-card, .set-row, .settings-head, ' +
    '.modal, .modal-body, .modal-foot, .dlg, .upd-dlg, .toast, .collapsed-mark'
  );
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    if (!n.getClientRects().length) continue;
    var st = getComputedStyle(n);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    var r = n.getBoundingClientRect();
    var issue = '';
    if (r.width < 1 || r.height < 1) issue = 'zero-size';
    else if (r.right > vw + 1 || r.bottom > vh + 1 || r.left < -1 || r.top < -1)
      issue = 'overflow ' + [r.left, r.top, r.right, vh].map(Math.round).join(',');
    if (issue) out.push({ sel: (n.className || n.id || '').toString().slice(0, 32), issue: issue });
  }
  // 可滚动容器里内容是否被永久截断（scrollHeight 远大于 clientHeight 且不可滚）
  var scrollers = document.querySelectorAll('.list-wrap, .settings-body, .modal-body');
  for (var j = 0; j < scrollers.length; j++) {
    var s = scrollers[j];
    if (!s.getClientRects().length) continue;
    var st2 = getComputedStyle(s);
    if (s.scrollHeight > s.clientHeight + 2 && st2.overflowY === 'hidden') {
      out.push({ sel: (s.className || '').toString().slice(0, 32), issue: 'clipped ' + s.scrollHeight + '>' + s.clientHeight });
    }
  }
  return JSON.stringify({ w: vw, h: vh, issues: out });
})()
"""

SWITCH_JS = r"""
(function(){
  // 逐个点「设置」里的开关，点完把前端状态与后端真实状态一起报回来
  var ids = ['setSnap', 'setCollapse', 'setAutoCollapse', 'setTop'];
  var snap = [];
  ids.forEach(function (id) {
    var n = document.getElementById(id);
    if (!n) { snap.push([id, 'missing']); return; }
    n.click();
    snap.push([id, n.classList.contains('is-on')]);
  });
  return JSON.stringify(snap);
})()
"""

STATE_JS = r"""
(function(){
  return JSON.stringify({
    body: document.body.className,
    todos: (window.__todoApp ? window.__todoApp.todos : []).length,
    filter: window.__todoApp ? window.__todoApp.getFilter() : '?'
  });
})()
"""


def main() -> None:
    state = appmod.load_state()
    state["snap"] = False
    state["auto_collapse"] = False
    state["collapse_min"] = False
    state["close_action"] = "quit"
    state["mini_preset"] = 1

    holder: dict = {}
    api = appmod.Api(appmod.Store(appmod.DATA_FILE), holder, state)
    window = webview.create_window(
        "audit",
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

    report: dict = {"errors": [], "steps": [], "layout": {}, "switch": [], "backend": {}}

    def js(code: str):
        return window.evaluate_js(code)

    def step(name: str, code: str):
        try:
            v = js(code)
        except Exception as exc:  # evaluate_js 抛错也要记，不能中断巡检
            v = "EXC: " + str(exc)[:200]
        report["steps"].append({"name": name, "value": v})
        return v

    def drain(name: str):
        raw = js(TAIL_JS)
        try:
            errs = json.loads(raw) if raw else []
        except Exception:
            errs = [str(raw)]
        for e in errs:
            report["errors"].append({"at": name, "err": e})

    def runner() -> None:
        time.sleep(2.8)
        js(HOOK_JS)

        # 1) 基础渲染
        report["layout"]["mini_empty"] = json.loads(js(LAYOUT_JS))
        drain("mini_empty")

        # 2) 添加三条真实任务
        step("add-1", """
          (function(){
            var i=document.getElementById('inputText');
            i.value='巡检任务A 明天 !高';
            document.getElementById('addBtn').click();
            i.value='巡检任务B 9点30分';
            document.getElementById('addBtn').click();
            i.value='巡检任务C 每周';
            document.getElementById('addBtn').click();
            return JSON.stringify(window.__todoApp.todos.map(function(t){
              return [t.title,t.priority,t.due,t.time,t.repeat];
            }));
          })()
        """)
        drain("add")

        # 3) 勾选 + 置顶
        step("toggle", """
          (function(){
            var A=window.__todoApp;
            A.toggle(A.todos[0].id);
            return JSON.stringify(A.todos.map(function(t){return [t.title,t.done];}));
          })()
        """)
        step("pin", """
          (function(){
            var A=window.__todoApp;
            A.togglePin(A.todos[1].id);
            return JSON.stringify(A.visibleTodos().map(function(t){return t.title+(t.pinned?'*':'');}));
          })()
        """)
        drain("toggle-pin")
        report["layout"]["mini_list"] = json.loads(js(LAYOUT_JS))

        # 4) 每个筛选都切一遍
        step("filters", """
          (function(){
            var out=[];
            ['today','pending','overdue','done','all'].forEach(function(f){
              var b=document.querySelector('[data-filter="'+f+'"]');
              if(b){ b.click(); out.push(f+':'+document.querySelectorAll('.todo-item').length); }
            });
            return out.join(' ');
          })()
        """)
        drain("filters")

        # 5) 编辑弹窗：打开、改内容、保存
        step("edit", """
          (function(){
            var A=window.__todoApp;
            document.querySelectorAll('.todo-item .edit-btn')[0].click();
            var mask=document.getElementById('modalMask');
            var open=!mask.hidden;
            var ta=document.getElementById('editText');
            var box=ta.getBoundingClientRect();
            var foot=document.querySelector('.modal-foot').getBoundingClientRect();
            var inView = foot.bottom <= innerHeight + 1 && foot.top >= 0;
            document.getElementById('editNote').value='巡检备注';
            ta.value='巡检任务A改';
            document.getElementById('editSave').click();
            return JSON.stringify({open:open, box:[Math.round(box.width),Math.round(box.height)],
              footInView:inView,
              saved:A.todos.some(function(t){return t.title==='巡检任务A改';})});
          })()
        """)
        time.sleep(0.4)
        drain("edit")
        report["layout"]["after_edit"] = json.loads(js(LAYOUT_JS))

        # 5b) 小卡片添加抽屉：输入区不能被底部栏顶掉
        step("adding", """
          (function(){
            document.getElementById('btnQuickAdd').click();
            var c=document.querySelector('.composer').getBoundingClientRect();
            return JSON.stringify({open:document.body.classList.contains('is-adding'),
              rect:[Math.round(c.left),Math.round(c.top),Math.round(c.right),Math.round(c.bottom)],
              inView:c.bottom<=innerHeight+1 && c.top>=0 && c.right<=innerWidth+1});
          })()
        """)
        time.sleep(0.4)
        report["layout"]["adding"] = json.loads(js(LAYOUT_JS))
        step("close-adding", "document.body.classList.remove('is-adding'); 'ok'")
        time.sleep(0.3)
        drain("adding")

        # 6) 设置页：布局 + 全部开关
        step("open-settings", "document.getElementById('btnSettingsMini').click(); 'ok'")
        time.sleep(0.6)
        report["layout"]["settings"] = json.loads(js(LAYOUT_JS))
        report["switch"] = json.loads(js(SWITCH_JS))
        time.sleep(0.9)
        report["backend"]["after_switches"] = json.loads(api.get_window_state())
        # 前端显示的开关状态（逐个读 class）
        report["switch_view"] = json.loads(js("""
          (function(){
            var o={};
            ['setSnap','setCollapse','setAutoCollapse','setTop'].forEach(function(id){
              var n=document.getElementById(id); o[id]=n?n.classList.contains('is-on'):null;
            });
            return JSON.stringify(o);
          })()
        """))
        drain("settings")
        step("close-settings", "document.getElementById('setBack').click(); 'ok'")
        time.sleep(0.5)

        # 7) 切完整模式 → 布局 → 切回
        step("to-full", "document.getElementById('btnMode').click(); 'ok'")
        time.sleep(1.4)
        report["layout"]["full"] = json.loads(js(LAYOUT_JS))
        report["state_full"] = json.loads(js(STATE_JS))
        drain("to-full")

        step("open-settings-full", "document.getElementById('btnSettings').click(); 'ok'")
        time.sleep(0.6)
        report["layout"]["settings_full"] = json.loads(js(LAYOUT_JS))
        step("close-settings-full", "document.getElementById('setBack').click(); 'ok'")
        time.sleep(0.4)
        step("to-mini", "document.getElementById('btnMode').click(); 'ok'")
        time.sleep(1.4)
        report["layout"]["back_mini"] = json.loads(js(LAYOUT_JS))
        drain("to-mini")

        # 8) 脏数据：磁盘/备份里混进非对象或字段缺失时不能白屏
        step("dirty", """
          (function(){
            var A=window.__todoApp;
            // 真实路径是 boot/restore 里的 normalizeTodos，这里照同一条路走
            A.todos=A.normalizeTodos([null, 'abc', {title:'没有id和字段'}, {id:'ok1',title:'正常',done:false}]);
            try { A.render(); return 'rendered:'+document.querySelectorAll('.todo-item').length; }
            catch(e){ return 'THROW:'+e.message; }
          })()
        """)
        drain("dirty")

        # 10) 清空后恢复
        step("reset", """
          (function(){
            var A=window.__todoApp;
            A.todos=[{id:'z1',title:'最后一条',priority:'medium',due:'',done:false,createdAt:1}];
            A.render();
            return document.querySelectorAll('.todo-item').length;
          })()
        """)
        drain("reset")

        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "layout"},
                         ensure_ascii=False, indent=2)[:4000])
        print("\n=== LAYOUT ===")
        for scope, data in report["layout"].items():
            print(f"{scope}: {data['w']}x{data['h']}", "OK" if not data["issues"] else data["issues"])
        os._exit(0)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
