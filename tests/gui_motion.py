"""动效/过渡巡检：把「看着别扭」的地方量化出来。

只测能客观判定的几件事：
  · 从空列表切回有内容的筛选，是不是整列表重播「下落进场」；
  · 删除条目是不是「啪」地消失（没有退场，后面的项瞬间补位）；
  · toast 是不是硬切消失（2.2 秒一到直接没）；
  · 勾选完成的颜色变化有没有过渡；
  · 有没有尊重系统的「减少动画」。

用法：venv/Scripts/python.exe tests/gui_motion.py
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
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-motion-")

import webview  # noqa: E402

import app as appmod  # noqa: E402

SEED = """
(function(){
  var A = window.__todoApp;
  A.todos = A.normalizeTodos([
    {id:'m1', title:'任务一', priority:'high', due:'', done:false, createdAt:9},
    {id:'m2', title:'任务二', priority:'medium', due:'', done:false, createdAt:8},
    {id:'m3', title:'任务三', priority:'medium', due:'', done:false, createdAt:7},
    {id:'m4', title:'任务四', priority:'low', due:'', done:false, createdAt:6},
    {id:'m5', title:'任务五', priority:'low', due:'', done:false, createdAt:5},
    {id:'m6', title:'任务六', priority:'low', due:'', done:false, createdAt:4},
    {id:'m7', title:'任务七', priority:'low', due:'', done:false, createdAt:3}
  ]);
  A.render();
  return document.querySelectorAll('.todo-item').length;
})()
"""

# 先切到「已完成」（空列表），再切回「全部」：修复前这 7 条都会重播进场
EMPTY_ROUNDTRIP = """
(function(){
  function chip(f){ return document.querySelector('.chip[data-filter="'+f+'"]'); }
  chip('done').click();
  var empty = document.querySelectorAll('.todo-item').length;
  chip('all').click();
  var enter = document.querySelectorAll('.todo-item.is-enter').length;
  var total = document.querySelectorAll('.todo-item').length;
  return JSON.stringify({empty:empty, enter:enter, total:total});
})()
"""

# 添加一条：只有这一条该播进场
ADD_ONLY_NEW = """
(function(){
  var inp = document.getElementById('inputText');
  inp.value = '新加的一条';
  document.getElementById('addBtn').click();
  var enter = document.querySelectorAll('.todo-item.is-enter');
  return JSON.stringify({
    enter: enter.length,
    title: enter.length ? enter[0].querySelector('.todo-title').textContent : ''
  });
})()
"""

DELETE_PROBE = """
(function(){
  var A = window.__todoApp;
  var li = document.querySelector('.todo-item');
  var id = li.getAttribute('data-id');
  var before = document.querySelectorAll('.todo-item').length;
  A.remove(id);
  var mid = document.querySelectorAll('.todo-item').length;
  var leaving = document.querySelectorAll('.todo-item.is-leaving').length;
  return JSON.stringify({id:id, before:before, mid:mid, leaving:leaving});
})()
"""

TOAST_SHOW = """
(function(){
  var A = window.__todoApp;
  A.toggle(A.todos[0].id);        // 会触发一次 toast（勾选/置顶不一定有，直接调内部）
  return document.getElementById('toast').hidden ? 'no-toast' : 'toast';
})()
"""

TOAST_STATE = """
(function(){
  var t = document.getElementById('toast');
  return JSON.stringify({
    hidden: t.hidden,
    hiding: t.classList.contains('is-hiding'),
    anim: getComputedStyle(t).animationName
  });
})()
"""

SCROLL_RESET = """
(function(){
  var wrap = document.querySelector('.list-wrap');
  wrap.scrollTop = 60;
  var scrolled = wrap.scrollTop;
  document.querySelector('.chip[data-filter="pending"]').click();
  return JSON.stringify({scrolled:scrolled, after:wrap.scrollTop});
})()
"""

DONE_COLOR = """
(function(){
  var A = window.__todoApp;
  var title = document.querySelector('.todo-title');
  var cs = getComputedStyle(title);
  return JSON.stringify({transition: cs.transitionProperty, duration: cs.transitionDuration});
})()
"""

# 主动挂上退场 class，确认 CSS 真的把动画换掉了（不靠时序采样）
EXIT_ANIM = """
(function(){
  var m = document.getElementById('modalMask');
  m.classList.add('is-closing');
  var modalAnim = getComputedStyle(m.querySelector('.modal')).animationName;
  m.classList.remove('is-closing');

  var t = document.getElementById('toast');
  t.hidden = false;
  t.classList.add('is-hiding');
  var toastAnim = getComputedStyle(t).animationName;
  t.classList.remove('is-hiding');
  t.hidden = true;

  return JSON.stringify({modal: modalAnim, toast: toastAnim});
})()
"""

# 保存失败曾经被静默吞掉：mock 后端返回 false，看前端有没有提示
SAVE_FAIL_START = """
(function(){
  var api = window.pywebview.api;
  var orig = api.save_todos;
  var t = document.getElementById('toast');
  t.textContent = '';
  t.hidden = true;
  window.__saveProbe = {done:false};
  api.save_todos = function(){ return Promise.resolve(false); };
  window.__todoApp.save().then(function(){
    api.save_todos = orig;
    window.__saveProbe = {done:true, text:t.textContent, hidden:t.hidden};
  });
  return 'started';
})()
"""

# 核心验收：真实窗口里，小卡片加完一条后抽屉必须自己收起来
ADD_CLOSE = """
(function(){
  var A = window.__todoApp;
  document.getElementById('btnQuickAdd').click();
  var opened = document.body.classList.contains('is-adding');
  document.getElementById('inputText').value = '真机添加测试';
  document.getElementById('addBtn').click();
  var closed = !document.body.classList.contains('is-adding');
  var has = A.todos.some(function(x){ return x.title === '真机添加测试'; });
  return JSON.stringify({opened:opened, closed:closed, added:has});
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
        "motion", url=str(ROOT / "ui" / "index.html"), js_api=api,
        width=380, height=560, min_size=(1, 1), frameless=True,
        easy_drag=False, transparent=False, shadow=True, on_top=True,
    )
    holder["window"] = window
    out: dict = {}

    def runner() -> None:
        step = "boot"

        def js(code):
            return window.evaluate_js(code)

        try:
            time.sleep(2.6)
            step = "seed"
            out["seed"] = js(SEED)
            time.sleep(0.4)
            step = "roundtrip"
            out["emptyRoundTrip"] = json.loads(js(EMPTY_ROUNDTRIP))
            time.sleep(0.5)
            step = "add"
            out["addOnlyNew"] = json.loads(js(ADD_ONLY_NEW))
            time.sleep(0.5)
            step = "scroll"
            out["scrollReset"] = json.loads(js(SCROLL_RESET))
            time.sleep(0.4)
            step = "delete"
            out["delete"] = json.loads(js(DELETE_PROBE))
            time.sleep(0.45)
            out["deleteAfter"] = js("document.querySelectorAll('.todo-item').length")
            step = "toast"
            js("window.__todoApp.toggle(window.__todoApp.todos[0].id); 'ok'")
            time.sleep(0.45)
            out["toastShown"] = json.loads(js(TOAST_STATE))
            time.sleep(1.85)      # 距显示约 2.3s：进场上限 0.32，退场 0.18 应该刚开始
            out["toastLater"] = json.loads(js(TOAST_STATE))
            step = "done-color"
            out["doneColor"] = json.loads(js(DONE_COLOR))
            step = "exit-anim"
            out["exitAnim"] = json.loads(js(EXIT_ANIM))
            step = "save-fail"
            js(SAVE_FAIL_START)
            for _ in range(12):
                time.sleep(0.1)
                probe = json.loads(js("JSON.stringify(window.__saveProbe)"))
                if probe.get("done"):
                    out["saveFail"] = probe
                    break
            else:
                out["saveFail"] = {"done": False}
            step = "add-close"
            out["addClose"] = json.loads(js(ADD_CLOSE))
            step = "reduced"
            out["reducedMotionRules"] = js(
                "Array.from(document.styleSheets).some(function(s){"
                "try{return Array.from(s.cssRules).some(function(r){"
                "return (r.conditionText||'').indexOf('reduced-motion')>=0;});}catch(e){return false;}})"
            )
        except Exception as exc:
            out["error"] = {"step": step, "msg": repr(exc)[:400]}
        finally:
            Path(__file__).resolve().parent.joinpath("gui_motion_result.json").write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(out, ensure_ascii=False, indent=2))
            sys.stdout.flush()
            os._exit(0)

    webview.start(runner, debug=False)


if __name__ == "__main__":
    main()
