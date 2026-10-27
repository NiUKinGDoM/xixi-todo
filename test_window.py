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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
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
