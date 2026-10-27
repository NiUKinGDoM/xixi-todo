"""窗口形态逻辑测试（无需真实 GUI）。

用假窗口对象替代 pywebview 的 Window，直接验证：
- min i ⇄ full 切换时的 resize / move 调用
- 切换前是否把当前位置记到旧模式
- 置顶开关的状态与落盘
- window.json 的读取与容错
- 边界情况（重复切换、非法模式、缺失坐标）

之所以不驱动真实窗口：pywebview 的 window.width 属性内部会等 shown 事件，
透明无边框窗口下事件时序不稳定，测试容易挂死。把逻辑与 GUI 分离更可靠。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 隔离测试数据目录，避免跑测试覆盖用户真实的待办数据
import tempfile
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-test-")

import app as appmod  # noqa: E402
from app import (  # noqa: E402
    COLLAPSE_LONG,
    COLLAPSE_THIN,
    FULL_H,
    FULL_W,
    MINI_H,
    MINI_W,
    STATE_FILE,
    Api,
    Store,
    clamp_to_screen,
    load_state,
    save_state,
)

RESULTS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(("OK   " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""))


class FakeScreen:
    def __init__(self, x=0, y=0, w=1920, h=1080):
        self.x, self.y, self.width, self.height = x, y, w, h


class FakeWindow:
    """记录调用，模拟 pywebview Window 的相关接口。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._x = 100
        self._y = 100
        self._w = MINI_W
        self._h = MINI_H
        self._on_top = True

    @property
    def x(self) -> int:
        return self._x

    @property
    def y(self) -> int:
        return self._y

    @property
    def width(self) -> int:
        return self._w

    @property
    def height(self) -> int:
        return self._h

    @property
    def on_top(self) -> bool:
        return self._on_top

    @on_top.setter
    def on_top(self, v: bool) -> None:
        self._on_top = bool(v)
        self.calls.append(("on_top", v))

    def resize(self, w: int, h: int, *a) -> None:
        self._w, self._h = w, h
        self.calls.append(("resize", w, h))

    def move(self, x: int, y: int) -> None:
        self._x, self._y = x, y
        self.calls.append(("move", x, y))

    def minimize(self) -> None:
        self.calls.append(("minimize",))

    def destroy(self) -> None:
        self.calls.append(("destroy",))


def fresh_state(mode: str = "mini") -> dict:
    return {
        "mode": mode,
        "on_top": True,
        "mini": {"x": 300, "y": 200, "w": MINI_W, "h": MINI_H},
        "full": {"x": 120, "y": 80, "w": FULL_W, "h": FULL_H},
    }


def main() -> int:
    if STATE_FILE.exists():
        STATE_FILE.unlink()

    store = Store(ROOT / "tests" / "win_test_todos.json")
    win = FakeWindow()
    holder = {"window": win}
    state = fresh_state("mini")
    api = Api(store, holder, state)

    # ---------- 初始状态 ----------
    st = json.loads(api.get_window_state())
    check("初始模式为 mini", st["mode"] == "mini", f"mode={st['mode']}")
    check("初始置顶为开", st["on_top"] is True, f"on_top={st['on_top']}")

    # ---------- mini -> full ----------
    win.calls.clear()
    api.set_mode("full")
    check("切 full 调用了 resize", ("resize", FULL_W, FULL_H) in win.calls, str(win.calls))
    check(
        "切 full 前记录了 mini 位置",
        state["mini"]["x"] == 100 and state["mini"]["y"] == 100,
        f"mini={state['mini']}",
    )
    check(
        "切 full 后移动到 full 的记录位置",
        ("move", 120, 80) in win.calls,
        str(win.calls),
    )
    check("状态模式已更新为 full", state["mode"] == "full", f"mode={state['mode']}")

    # ---------- 重复切同一模式应无操作 ----------
    win.calls.clear()
    api.set_mode("full")
    check("重复切同一模式不再 resize", ("resize", FULL_W, FULL_H) not in win.calls, str(win.calls))

    # ---------- full -> mini ----------
    win._x, win._y = 500, 300
    win.calls.clear()
    api.set_mode("mini")
    check("切回 mini 调用了 resize", ("resize", MINI_W, MINI_H) in win.calls, str(win.calls))
    check(
        "切回 mini 前记录了 full 位置",
        state["full"]["x"] == 500 and state["full"]["y"] == 300,
        f"full={state['full']}",
    )
    # mini 槽位在第一次切走时已被快照为当时实位 (100,100)，因此应回到那里，
    # 而不是恢复到测试初始设定的 (300,200)。这符合“记住上次所在位置”的语义。
    check(
        "切回 mini 后移动到 mini 上次实际位置",
        ("move", 100, 100) in win.calls,
        str(win.calls),
    )

    # ---------- 非法模式 ----------
    win.calls.clear()
    api.set_mode("huge")
    check("非法模式不触发 resize", not any(c[0] == "resize" for c in win.calls), str(win.calls))
    check("非法模式不改变当前模式", state["mode"] == "mini", f"mode={state['mode']}")

    # ---------- 置顶开关 ----------
    win.calls.clear()
    before = state["on_top"]
    api.toggle_on_top()
    check("置顶状态被翻转", state["on_top"] is not before, f"{before} -> {state['on_top']}")
    check("窗口 on_top 已应用", ("on_top", state["on_top"]) in win.calls, str(win.calls))
    api.toggle_on_top()
    check("再次切换回到原值", state["on_top"] is before, f"on_top={state['on_top']}")

    # ---------- 落盘 ----------
    save_state(state)
    check("window.json 已生成", STATE_FILE.exists(), str(STATE_FILE))
    saved = json.loads(STATE_FILE.read_text("utf-8"))
    check("落盘模式正确", saved["mode"] == state["mode"], f"mode={saved['mode']}")
    check("落盘包含两种模式的位置", "mini" in saved and "full" in saved)
    check("落盘 mini 尺寸正确", saved["mini"]["w"] == MINI_W, f"w={saved['mini']['w']}")

    # ---------- 读取 ----------
    loaded = load_state()
    check("读回模式一致", loaded["mode"] == state["mode"], f"mode={loaded['mode']}")
    check("读回置顶一致", loaded["on_top"] == state["on_top"])

    # ---------- 损坏文件容错 ----------
    STATE_FILE.write_text("{ 这不是 json", encoding="utf-8")
    recovered = load_state()
    check("损坏状态文件不崩溃", isinstance(recovered, dict))
    check("损坏时回落到 mini", recovered["mode"] == "mini", f"mode={recovered['mode']}")
    check("损坏时回落到置顶开", recovered["on_top"] is True)

    # ---------- 屏幕钳制 ----------
    import app as app_module

    _orig_screens = webview_screens = getattr(app_module, "webview", None)
    class _FakeWebview:
        screens = [FakeScreen()]
    app_module.webview = _FakeWebview()

    try:
        x, y = clamp_to_screen(1000, 300, 380, 560)
        check("屏幕内的小卡片位置不变", (x, y) == (1000, 300), f"得到 {x},{y}")

        x, y = clamp_to_screen(1800, 900, MINI_W, MINI_H)
        check(
            "贴边小卡片被收进屏幕",
            x + MINI_W <= 1920 and y + MINI_H <= 1080,
            f"得到 {x},{y} 右缘={x + MINI_W} 下缘={y + MINI_H}",
        )

        x, y = clamp_to_screen(1512, 432, FULL_W, FULL_H)
        check(
            "大窗口展开后被拉回屏幕内",
            x + FULL_W <= 1920 and y + FULL_H <= 1080 and x >= 8 and y >= 8,
            f"得到 {x},{y} 右缘={x + FULL_W} 下缘={y + FULL_H}",
        )

        x, y = clamp_to_screen(-300, -200, 380, 560)
        check("负坐标被拉回可见区", x >= 8 and y >= 8, f"得到 {x},{y}")

        x, y = clamp_to_screen(0, 0, 2400, 1400)
        check(
            "窗口大于屏幕时贴左上留边距",
            x == 8 and y == 8,
            f"得到 {x},{y}",
        )
    finally:
        if webview_screens is not None:
            app_module.webview = webview_screens

    # ---------- 无窗口时的健壮性 ----------
    api2 = Api(store, {"window": None}, fresh_state("mini"))
    try:
        api2.set_mode("full")
        api2.toggle_on_top()
        api2.minimize_window()
        api2.close_window()
        check("无窗口对象时不抛异常", True)
    except Exception as exc:  # noqa: BLE001
        check("无窗口对象时不抛异常", False, repr(exc))

    # ---------- 关闭时保存位置 ----------
    win3 = FakeWindow()
    win3._x, win3._y = 777, 444
    state3 = fresh_state("mini")
    api3 = Api(store, {"window": win3}, state3)
    api3.close_window()
    check("关闭时记录了当前位置", state3["mini"]["x"] == 777 and state3["mini"]["y"] == 444,
          f"mini={state3['mini']}")
    check("关闭时调用了 destroy", ("destroy",) in win3.calls, str(win3.calls))
    # ---------- 收进屏幕边缘 ----------

    # 用一个假的屏幕几何，避免依赖真实分辨率
    class _FakeScr:
        x, y, width, height = 0, 0, 1920, 1080

    orig_screens = appmod.webview.screens
    appmod.webview.screens = [_FakeScr()]
    orig_rect = appmod._window_rect
    orig_hwnd = appmod._hwnd_of

    api_c = Api(Store(ROOT / "tests" / "win_test_todos.json"), {"window": None}, {
        "mode": "mini", "on_top": True, "snap": True,
        "app_name": "t", "mini_preset": 1,
        "collapsed": False, "collapse_edge": "",
        "mini": {"x": None, "y": None, "w": 380, "h": 560},
        "full": {"x": None, "y": None, "w": 1080, "h": 720},
    })

    def fake_geom(rect_tuple):
        appmod._window_rect = lambda hwnd: rect_tuple
        appmod._hwnd_of = lambda win: 1234

    fake_geom((1540, 300, 380, 560))          # 右缘正好贴屏
    check("识别出贴近右边缘", api_c._nearest_edge(object()) == "right",
          str(api_c._nearest_edge(object())))

    fake_geom((4, 300, 380, 560))             # 贴左
    check("识别出贴近左边缘", api_c._nearest_edge(object()) == "left")

    fake_geom((700, 240, 380, 560))           # 四边都不靠
    check("远离边缘时不吸附", api_c._nearest_edge(object()) is None,
          str(api_c._nearest_edge(object())))

    fake_geom((700, 2, 380, 560))             # 贴上
    check("识别出贴近上边缘", api_c._nearest_edge(object()) == "top")

    fake_geom((700, 520, 380, 560))           # 下缘 1080
    check("识别出贴近下边缘", api_c._nearest_edge(object()) == "bottom")

    # 收起尺寸：竖向/横向薄条
    check("薄条长宽符合设计", COLLAPSE_THIN == 20 and COLLAPSE_LONG == 104,
          f"{COLLAPSE_THIN}x{COLLAPSE_LONG}")

    # 状态里带上收起字段
    st = json.loads(api_c.get_window_state())
    check("状态包含 collapsed", "collapsed" in st and st["collapsed"] is False, str(st)[:80])
    check("状态包含 collapse_edge", st.get("collapse_edge") == "", str(st)[:80])

    # 收起时快照不写入尺寸（否则会把小条尺寸当成卡片尺寸）
    api_c.state["collapsed"] = True
    api_c.state["mini"] = {"x": 1, "y": 2, "w": 380, "h": 560}
    api_c._snapshot("mini")
    check("收起状态下快照不改尺寸",
          api_c.state["mini"]["w"] == 380 and api_c.state["mini"]["h"] == 560,
          str(api_c.state["mini"]))
    api_c.state["collapsed"] = False

    # ---------- 最小化是否收边 ----------

    class _FakeWin:
        def __init__(self):
            self.sizes = []
            self.moves = []
            self.minimized = 0

        def resize(self, w, h):
            self.sizes.append((w, h))

        def move(self, x, y):
            self.moves.append((x, y))

        def minimize(self):
            self.minimized += 1
            return True

    # 窗口在屏幕中间（离四边都很远）也要收边：之前要求贴边才收，点完没反应
    fake_geom((700, 300, 380, 560))
    fw = _FakeWin()
    holder = {"window": fw}
    api_c.window_holder = holder
    api_c.state["collapsed"] = False
    api_c.state["collapse_min"] = True
    out = json.loads(api_c.minimize_window())
    check("中间位置最小化也收边", out.get("collapsed") is True, str(out)[:80])
    check("收边后尺寸变薄条", fw.sizes and fw.sizes[-1] in ((20, 104), (104, 20)),
          str(fw.sizes))
    check("收边时不调系统最小化", fw.minimized == 0, f"minimized={fw.minimized}")

    # 关掉开关 → 退回系统最小化，返回空
    api_c.state["collapsed"] = False
    api_c.state["collapse_min"] = False
    fw2 = _FakeWin()
    api_c.window_holder = {"window": fw2}
    out2 = api_c.minimize_window()
    check("关掉收边后走系统最小化", out2 == "" and fw2.minimized == 1, str(out2))

    # 开关本身要落盘
    api_c.set_collapse_min("1")
    check("收边开关写入状态", api_c.state["collapse_min"] is True)
    saved = json.loads(STATE_FILE.read_text("utf-8"))
    check("收边开关已落盘", saved.get("collapse_min") is True, str(saved)[:80])

    # 自启动：测试目录下不写真实注册表，只回读
    before = appmod.is_autostart_enabled()
    got = json.loads(api_c.set_autostart("1"))
    check("自启动接口不抛异常", isinstance(got.get("autostart"), bool), str(got)[:80])
    check("测试模式不动注册表", appmod.is_autostart_enabled() == before)

    # ---------- 展开：按当前模式还原 ----------

    fake_geom((243, 143, 1080, 720))
    fw3 = _FakeWin()
    api_c.window_holder = {"window": fw3}
    api_c.state.update({
        "mode": "full", "collapsed": False, "collapse_edge": "",
        "collapse_min": True,
        "full": {"x": 243, "y": 143, "w": 1080, "h": 720},
    })
    api_c.collapse_window("top")
    check("完整视图收起后记住原尺寸", api_c.state["full"]["w"] == 1080,
          str(api_c.state["full"]))
    api_c.state["collapsed"] = True
    out3 = json.loads(api_c.expand_window())
    check("展开后回到完整尺寸", out3.get("collapsed") is False and fw3.sizes[-1] == (1080, 720),
          str(fw3.sizes))
    check("展开后回到原位置", fw3.moves and fw3.moves[-1] == (243, 143), str(fw3.moves[-1:]))
    check("展开后短暂不吸附", api_c._suppress_snap_until > appmod.time.monotonic())

    # ---------- 贴边自动收起 / 关闭行为 ----------

    api_c.set_auto_collapse("")
    check("贴边自动收起可关闭", api_c.state["auto_collapse"] is False)
    api_c.set_auto_collapse("1")
    check("贴边自动收起可打开", api_c.state["auto_collapse"] is True)

    api_c.set_close_action("tray")
    check("关闭行为可切到托盘", api_c.state["close_action"] == "tray")
    api_c.set_close_action("quit")
    saved2 = json.loads(STATE_FILE.read_text("utf-8"))
    check("关闭行为已落盘", saved2.get("close_action") == "quit", str(saved2)[:80])
    api_c.set_close_action("乱写")
    check("非法关闭行为被忽略", api_c.state["close_action"] == "quit")

    # 托盘模式：关闭只隐藏，不退出；退出模式：直接退出
    called = {"hide": 0, "quit": 0}
    api_c._hide_to_tray = lambda: (called.__setitem__("hide", called["hide"] + 1) or True)
    api_c.quit_app = lambda: called.__setitem__("quit", called["quit"] + 1)
    api_c.state["close_action"] = "tray"
    api_c.close_window()
    check("托盘模式下关闭不退出", called["hide"] == 1 and called["quit"] == 0, str(called))
    api_c.state["close_action"] = "quit"
    api_c.close_window()
    check("退出模式下关闭直接退出", called["quit"] == 1, str(called))

    # 拖动期间抑制吸附
    api_c.set_dragging("1")
    check("拖动标记可置位", api_c._dragging is True)
    api_c.set_dragging("")
    check("拖动标记可清除", api_c._dragging is False)

    appmod._window_rect = orig_rect
    appmod._hwnd_of = orig_hwnd
    appmod.webview.screens = orig_screens

    check("关闭时已落盘", STATE_FILE.exists())

    print("\n===== 窗口形态逻辑测试 =====")
    for r in RESULTS:
        print(r)
    failed = [r for r in RESULTS if r.startswith("FAIL")]
    print(f"\n通过 {len(RESULTS) - len(failed)} / {len(RESULTS)}")

    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        tmp = ROOT / "tests" / "win_test_todos.json"
        if tmp.exists():
            tmp.unlink()
    except Exception:
        pass

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
