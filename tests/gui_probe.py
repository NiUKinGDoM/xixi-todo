"""真实窗口按钮可用性探针。

启动一个真正的 pywebview 窗口（WebView2），用 DOM click 逐个点按钮，
每点一次都用三种手段确认界面还活着：

1. evaluate_js 是否能在超时内返回（UI 线程还能执行脚本）
2. IsHungAppWindow(hwnd) 是否报告窗口卡死
3. 进程是否还在

一旦某个按钮把界面弄死，脚本立刻把它的 id 写进 tests/gui_probe.log 并退出，
这样能精确定位是哪个按钮、走了哪条后端路径。

用法：venv/Scripts/python.exe tests/gui_probe.py
"""

from __future__ import annotations

import ctypes
import faulthandler
import json
import os
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 必须隔离数据目录，绝不能碰用户真实待办
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-probe-")

import webview  # noqa: E402

import app as appmod  # noqa: E402

LOG = Path(__file__).resolve().parent / "gui_probe.log"
OUT = Path(__file__).resolve().parent / "gui_probe_result.json"

user32 = ctypes.windll.user32


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def hwnd_of(window) -> int:
    try:
        return int(window.native.Handle.ToInt64()) if hasattr(window, "native") else 0
    except Exception:
        return 0


def is_hung(hwnd: int) -> bool:
    if not hwnd:
        return False
    try:
        return bool(user32.IsHungAppWindow(hwnd))
    except Exception:
        return False


def eval_with_timeout(window, script: str, timeout: float = 4.0):
    """在单独线程里跑 evaluate_js；超时就说明 UI 线程被堵死。"""
    box: dict = {}

    def run() -> None:
        try:
            box["v"] = window.evaluate_js(script)
        except Exception as exc:  # noqa: BLE001
            box["e"] = repr(exc)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return False, None
    return True, box.get("v", box.get("e"))


STEPS: list[tuple[str, str]] = [
    # (说明, 要执行的 JS)
    ("baseline: 页面就绪", "document.readyState"),
    ("置顶按钮 btnPin", "document.getElementById('btnPin').click()"),
    ("再点一次 btnPin", "document.getElementById('btnPin').click()"),
    ("打开设置（迷你齿轮）", "document.getElementById('btnSettingsMini').click()"),
    ("设置页-置顶开关 setTop", "document.getElementById('setTop').click()"),
    ("设置页-自动贴边 setSnap", "document.getElementById('setSnap').click()"),
    ("设置页-贴边自动收起 setAutoCollapse", "document.getElementById('setAutoCollapse').click()"),
    ("设置页-最小化收边 setCollapse", "document.getElementById('setCollapse').click()"),
    ("设置页-尺寸档位 紧凑", "document.querySelector('#setSize button[data-preset=\"0\"]').click()"),
    ("设置页-尺寸档位 标准", "document.querySelector('#setSize button[data-preset=\"1\"]').click()"),
    ("设置页-关闭动作 收进托盘", "document.querySelector('#setCloseAction button[data-close=\"tray\"]').click()"),
    ("设置页-关闭动作 退出", "document.querySelector('#setCloseAction button[data-close=\"quit\"]').click()"),
    ("设置页-改名保存", "var n=document.getElementById('setName');n.value='探针名';document.getElementById('setNameSave').click()"),
    ("设置页-清除已完成", "document.getElementById('menuClearDone').click()"),
    ("设置页-返回", "document.getElementById('setBack').click()"),
    ("切换到完整视图 btnMode", "document.getElementById('btnMode').click()"),
    ("完整视图-侧边栏设置入口", "document.getElementById('btnSettings').click()"),
    ("完整视图-设置返回", "document.getElementById('setBack').click()"),
    ("筛选-今天", "document.querySelector('.chip[data-filter=\"today\"]').click()"),
    ("筛选-全部", "document.querySelector('.chip[data-filter=\"all\"]').click()"),
    ("添加一条待办", "var i=document.getElementById('inputText');i.value='探针任务';document.getElementById('addBtn').click()"),
    ("添加带重复语法的待办", "var i=document.getElementById('inputText');i.value='每天喝水 每天';document.getElementById('addBtn').click()"),
    ("标记完成（第一条）", "document.querySelector('.todo-item .check').click()"),
    ("切回迷你 btnMode", "document.getElementById('btnMode').click()"),
    ("最小化收边 btnMin", "document.getElementById('btnMin').click()"),
    ("从边缘展开", "document.getElementById('collapsedMark').click()"),
]


def main() -> None:
    LOG.write_text("", encoding="utf-8")
    # 卡住时把每个线程的调用栈打出来，定位死锁点
    _fh = LOG.open("a", encoding="utf-8")
    faulthandler.dump_traceback_later(25, repeat=True, file=_fh)

    state = appmod.load_state()
    state["snap"] = False          # 排除自动贴边干扰
    state["auto_collapse"] = False
    state["collapse_min"] = True
    state["close_action"] = "quit"
    state["mode"] = "mini"

    holder: dict = {}
    store = appmod.Store(appmod.DATA_FILE)
    api = appmod.Api(store, holder, state)

    def probe(path: str = "/") -> str:
        return "pong"

    api.probe = probe

    index = ROOT / "ui" / "index.html"
    window = webview.create_window(
        "probe",
        url=str(index),
        js_api=api,
        width=380,
        height=560,
        min_size=(1, 1),
        frameless=True,
        easy_drag=False,
        transparent=False,
        shadow=True,
        on_top=True,
        text_select=True,
    )
    holder["window"] = window

    results: list[dict] = []
    dead = {"step": None}

    def runner() -> None:
        time.sleep(2.5)  # 等页面与 js_api 桥接就绪
        hwnd = 0
        try:
            import webview as wv

            win = wv.windows[0]
            hwnd = int(win.native.Handle.ToInt64())
        except Exception as exc:  # noqa: BLE001
            log(f"取句柄失败: {exc}")

        ok, val = eval_with_timeout(window, "1+1", 5)
        log(f"bridge ready ok={ok} val={val} hwnd={hwnd}")

        for label, script in STEPS:
            t0 = time.time()
            log(f"... 点击前 {label}")
            ok, val = eval_with_timeout(window, script, 3.5)
            cost = round((time.time() - t0) * 1000)
            hung = is_hung(hwnd)
            alive = not hung
            results.append({"step": label, "ok": ok, "ms": cost, "hung": hung, "val": val})
            log(f"{'OK  ' if ok and alive else 'DEAD'} {label} :: {cost}ms hung={hung} val={val}")
            if not ok or hung:
                dead["step"] = label
                break
            time.sleep(0.55)
            # 每一步后再确认一次界面仍可执行脚本
            ok2, _ = eval_with_timeout(window, "1", 2.5)
            log(f"... 点击后自检 {label} ok={ok2}")
            if not ok2:
                dead["step"] = label + "（点击后界面无响应）"
                log(f"DEAD 点击「{label}」之后界面不再响应")
                break

        OUT.write_text(
            json.dumps({"dead": dead["step"], "steps": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log(f"probe done, dead={dead['step']}")

        # 立刻退出，避免卡死的窗口拖住进程
        time.sleep(0.2)
        os._exit(0 if dead["step"] is None else 2)

    try:
        webview.start(runner, debug=False)
    except Exception:
        log("webview.start 异常:\n" + traceback.format_exc())
        os._exit(3)


if __name__ == "__main__":
    main()
