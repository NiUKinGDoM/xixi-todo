"""新增功能的后端逻辑测试：文件存储、备份导出/导入、提醒判定。

不需要真实 GUI：文件对话框用假窗口对象返回临时路径，
这样能真正验证「写入文件 / 读回文件」这条链路。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 隔离测试数据目录，避免跑测试覆盖用户真实的待办数据
import tempfile
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-test-")

from app import Api, JsonList, Store  # noqa: E402

RESULTS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(("OK   " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""))


class FakeWindow:
    """按预设值返回文件对话框结果。"""

    def __init__(self, dialog_result=None):
        self.dialog_result = dialog_result
        self.calls: list[tuple] = []

    def create_file_dialog(self, dialog_type, **kwargs):
        self.calls.append((dialog_type, kwargs))
        return self.dialog_result


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="todo-test-"))
    todos_path = tmp / "todos.json"

    store = Store(todos_path)

    # ---------- JsonList 基础（提醒记录用的就是这个容器） ----------
    side_path = tmp / "side.json"
    side_store = JsonList(side_path)
    check("文件初始为空", side_store.load() == [])
    check("写入成功", side_store.save(["a", "b"]))
    check("读回一致", side_store.load() == ["a", "b"])

    side_path.write_text("{坏掉的", encoding="utf-8")
    check("文件损坏时不崩溃", side_store.load() == [])
    check("损坏文件被备份", any(tmp.glob("side.json.corrupt")))

    api = Api(store, {"window": None}, {
        "mode": "mini", "on_top": True,
        "mini": {"x": None, "y": None, "w": 380, "h": 560},
        "full": {"x": None, "y": None, "w": 1080, "h": 720},
    })
    check("分组接口已移除", not hasattr(api, "save_groups") and not hasattr(api, "load_groups"))

    # ---------- 备份导出 ----------
    backup_file = tmp / "backup.json"
    payload = json.dumps({"version": 3, "todos": [{"id": "b1", "title": "备份任务"}]},
                         ensure_ascii=False)
    win = FakeWindow(dialog_result=[str(backup_file)])
    api2 = Api(store, {"window": win}, None)
    result = api2.export_backup(payload)

    check("导出返回了路径", bool(result), result)
    check("备份文件已生成", backup_file.exists())
    if backup_file.exists():
        saved = json.loads(backup_file.read_text("utf-8"))
        check("备份内容正确", saved["todos"][0]["title"] == "备份任务", str(saved)[:80])
    check("导出时传入了 save 类型对话框", win.calls and win.calls[0][0] == 30,
          str(win.calls[0][0]) if win.calls else "无调用")

    # 取消对话框
    win_cancel = FakeWindow(dialog_result=None)
    api3 = Api(store, {"window": win_cancel}, None)
    check("取消导出返回空串", api3.export_backup(payload) == "")

    # ---------- 备份导入 ----------
    win_open = FakeWindow(dialog_result=[str(backup_file)])
    api4 = Api(store, {"window": win_open}, None)
    text = api4.import_backup()
    check("导入读回文件内容", "备份任务" in text, text[:60])
    check("导入时传入了 open 类型对话框", win_open.calls and win_open.calls[0][0] == 10,
          str(win_open.calls[0][0]) if win_open.calls else "无调用")

    win_open_cancel = FakeWindow(dialog_result=None)
    api5 = Api(store, {"window": win_open_cancel}, None)
    check("取消导入返回空串", api5.import_backup() == "")

    # 文件不存在时不抛异常
    win_missing = FakeWindow(dialog_result=[str(tmp / "不存在.json")])
    api6 = Api(store, {"window": win_missing}, None)
    check("导入不存在的文件不抛异常", api6.import_backup() == "")

    # 无窗口对象时不抛异常
    api7 = Api(store, {"window": None}, None)
    check("无窗口时导出返回空串", api7.export_backup(payload) == "")
    check("无窗口时导入返回空串", api7.import_backup() == "")

    # ---------- 待办数据里新增字段能原样往返 ----------
    rich = [{
        "id": "r1", "title": "带全部字段", "priority": "high",
        "due": "2026-11-01", "time": "09:30", "repeat": "weekly",
        "note": "备注内容", "done": False,
        "createdAt": 123, "order": 10, "doneCount": 3,
    }]
    api.save_todos(json.dumps(rich, ensure_ascii=False))
    back = json.loads(api.load_todos())
    check("新字段完整往返", back == rich, str(back)[:120])

    # ---------- 提醒键设计：重复任务换日期后应重新提醒 ----------
    # 提醒循环用 id|due|time 作为键，这里验证键随日期变化
    key1 = "r1|2026-11-01|09:30"
    key2 = "r1|2026-11-08|09:30"
    check("提醒键随日期变化（重复任务会再次提醒）", key1 != key2)

    # ---------- 提醒判定（纯函数） ----------
    from app import collect_reminders

    today = "2026-10-27"
    base = {"priority": "medium", "group": "", "note": "", "repeat": "none"}

    items = [
        dict(base, id="a", title="今天有时间的", due=today, time="09:00", done=False),
        dict(base, id="b", title="今天没时间的", due=today, time="", done=False),
        dict(base, id="c", title="昨天逾期", due="2026-10-26", time="", done=False),
        dict(base, id="d", title="已完成", due=today, time="08:00", done=True),
        dict(base, id="e", title="明天的", due="2026-10-28", time="09:00", done=False),
        dict(base, id="f", title="没日期的", due="", time="09:00", done=False),
    ]

    notif = collect_reminders(items, today, "08:30", set())
    keys = [k for k, _, _, _ in notif]
    check("未到点不提醒定时任务", "a|2026-10-27|09:00" not in keys, str(keys))
    check("无时间的今天任务会提醒", "b|2026-10-27|day" in keys, str(keys))
    check("逾期任务会提醒", "c|2026-10-26|overdue" in keys, str(keys))
    check("已完成任务不提醒", not any(k.startswith("d|") for k in keys), str(keys))
    check("未来任务不提醒", not any(k.startswith("e|") for k in keys), str(keys))
    check("无日期任务不提醒", not any(k.startswith("f|") for k in keys), str(keys))

    notif2 = collect_reminders(items, today, "09:00", set())
    keys2 = [k for k, _, _, _ in notif2]
    check("到点后提醒定时任务", "a|2026-10-27|09:00" in keys2, str(keys2))
    shown = {k: s for k, _, _, s in notif2}
    check("准点提醒会弹窗", shown.get("a|2026-10-27|09:00") is True, str(shown))

    # 已提醒过的不会重复
    already = set(keys2)
    notif3 = collect_reminders(items, today, "09:00", already)
    check("已提醒过不重复", notif3 == [], str(notif3))

    # 宽限期：过了 6 小时仍会记录，但不弹窗
    notif_late = collect_reminders(items, today, "20:00", set())
    late_map = {k: s for k, _, _, s in notif_late}
    key_a = "a|2026-10-27|09:00"
    check("迟到 11 小时仍会记录", key_a in late_map, str(list(late_map)))
    check("迟到太久不弹窗打扰", late_map.get(key_a) is False, str(late_map.get(key_a)))

    # 宽限期内（4 小时）应弹窗
    notif_grace = collect_reminders(items, today, "13:00", set())
    grace_map = {k: s for k, _, _, s in notif_grace}
    check("宽限期内仍弹窗", grace_map.get(key_a) is True, str(grace_map.get(key_a)))

    # 重复任务换日期后应重新提醒
    rolled = [dict(items[0], due="2026-10-28")]
    notif4 = collect_reminders(rolled, "2026-10-28", "09:05", already)
    check("重复任务到新日期会再提醒", len(notif4) == 1, str(notif4))

    # 提醒内容取任务标题
    notif5 = collect_reminders([dict(base, id="g", title="开会", due=today, time="", done=False)],
                               today, "10:00", set())
    check("提醒文案带任务标题", notif5 and notif5[0][2] == "开会", str(notif5))

    # ---------- 应用内更新：启动安装程序的命令 ----------
    # 回归点：这条命令曾拆成 ["cmd", "/c", ...] 传进去，subprocess 把内层
    # 引号转义成 \"，cmd 不认这种转义，start 就去打开一个叫「\」的文件，
    # 弹出「Windows 找不到 '\' 文件」。必须整条字符串原样交给 CreateProcess。
    import subprocess as _sp
    import threading as _th

    fake_setup = tmp / "xixi-todo-setup.exe"
    fake_setup.write_bytes(b"MZ")  # 只要存在就行，不会真执行

    captured: dict = {}

    class _FakePopen:
        def __init__(self, args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

    class _FakeTimer:
        def __init__(self, *a, **k):
            pass

        def start(self):
            pass

    real_popen, real_timer = _sp.Popen, _th.Timer
    _sp.Popen, _th.Timer = _FakePopen, _FakeTimer
    try:
        api_upd = Api(store, {})
        api_upd._dl["path"] = str(fake_setup)
        launched = api_upd.install_update()
    finally:
        _sp.Popen, _th.Timer = real_popen, real_timer

    args = captured.get("args")
    check("更新：能发起安装", launched is True, str(launched))
    check("更新：命令以字符串传递（不拆成列表）",
          isinstance(args, str), type(args).__name__)
    check("更新：路径被引号完整包住",
          isinstance(args, str) and f'"{fake_setup}"' in args, str(args)[:120])
    check("更新：不会再出现被转义的 \\\"",
          isinstance(args, str) and '\\"' not in args, str(args)[:120])
    check("更新：等待安装结束再返回",
          isinstance(args, str) and "/wait" in args, str(args)[:120])
    check("更新：静默安装参数齐全",
          isinstance(args, str) and "/SILENT" in args and "/CLOSEAPPLICATIONS" in args,
          str(args)[:120])
    check("更新：脱离父进程（父进程退出后仍继续）",
          bool(captured.get("kwargs", {}).get("creationflags", 0) & 0x00000008),
          str(captured.get("kwargs", {}).get("creationflags")))

    # ---------- 状态落盘：多进程不会撞同一个临时文件 ----------
    import subprocess as _sp2
    state_path = tmp / "state.json"
    code = (
        "import sys, json, pathlib\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from app import _atomic_write_text\n"
        f"p = pathlib.Path({str(state_path)!r})\n"
        "for i in range(40):\n"
        "    _atomic_write_text(p, json.dumps({'i': i}))\n"
    )
    procs = [_sp2.Popen([sys.executable, "-c", code]) for _ in range(3)]
    codes = [p.wait() for p in procs]
    check("并发写同一个状态文件不报错", all(c == 0 for c in codes), str(codes))
    try:
        json.loads(state_path.read_text(encoding="utf-8"))
        ok_json = True
    except Exception as exc:
        ok_json = False
        detail_json = str(exc)
    check("并发写后文件仍是合法 JSON", ok_json, "" if ok_json else detail_json)
    leftovers = list(tmp.glob("state.json.*.tmp"))
    check("没有残留临时文件", not leftovers, str(leftovers)[:80])

    print("\n===== 新功能后端测试 =====")
    for r in RESULTS:
        print(r)
    failed = [r for r in RESULTS if r.startswith("FAIL")]
    print(f"\n通过 {len(RESULTS) - len(failed)} / {len(RESULTS)}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
