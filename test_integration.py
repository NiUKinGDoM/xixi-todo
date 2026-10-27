"""桌面壳集成测试：验证 pywebview 启动、JS API 桥接、数据持久化全链路。

在真实的 WebView2 窗口中打开界面，执行数据读写，然后断言磁盘文件内容正确。
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# 隔离测试数据目录，避免跑测试覆盖用户真实的待办数据
import tempfile
os.environ["XIXI_TODO_DATA_DIR"] = tempfile.mkdtemp(prefix="xixi-test-")

import webview  # noqa: E402

from app import DATA_FILE, Store, _data_dir  # noqa: E402

RESULTS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(("OK   " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""))


def main() -> int:
    # 清空旧数据，保证测试从干净状态开始
    if DATA_FILE.exists():
        DATA_FILE.unlink()

    store = Store(DATA_FILE)

    # 单元层：Store 读写
    check("Store 初始为空", store.load() == [])
    check("Store 写入", store.save([{"id": "x", "title": "单元测试"}]))
    check("Store 读回", store.load() == [{"id": "x", "title": "单元测试"}])
    check("数据文件已落盘", DATA_FILE.exists(), str(DATA_FILE))

    # 损坏文件容错
    DATA_FILE.write_text("{ 坏掉的 json", encoding="utf-8")
    check("损坏数据不崩溃", store.load() == [])
    check("损坏文件已备份", any(DATA_FILE.parent.glob("*.corrupt")))

    # 恢复干净状态
    if DATA_FILE.exists():
        DATA_FILE.unlink()

    # 预置数据：用于验证「真实启动路径」能否自动加载磁盘数据
    # （不能手动调用 boot()，否则会掩盖启动逻辑的 bug）
    seeded = [
        {"id": "p1", "title": "预置任务甲", "priority": "high", "due": "", "done": False, "createdAt": 2},
        {"id": "p2", "title": "预置任务乙", "priority": "low", "due": "", "done": False, "createdAt": 1},
    ]
    store.save(seeded)

    holder: dict = {}
    from app import Api

    api = Api(store, holder)

    index = ROOT / "ui" / "index.html"
    check("界面文件存在", index.exists(), str(index))

    window = webview.create_window(
        "待办事项-集成测试",
        url=str(index),
        js_api=api,
        width=900,
        height=620,
        background_color="#EEF1F8",
    )
    holder["window"] = window

    def run_js():
        try:
            time.sleep(3.5)  # 等待页面加载 + pywebviewready + 自动 boot

            # 1) 桥接可用性
            ready = window.evaluate_js("typeof window.pywebview !== 'undefined'")
            check("pywebview 桥接已注入", ready is True, f"typeof={ready}")

            has_api = window.evaluate_js(
                "!!(window.pywebview && window.pywebview.api && "
                "typeof window.pywebview.api.save_todos === 'function')"
            )
            check("save_todos API 已暴露", has_api is True, f"result={has_api}")

            # 2) 【核心】真实启动路径：不手动 boot，检查页面是否自动加载了磁盘数据
            dom_count = window.evaluate_js("document.querySelectorAll('.todo-item').length")
            check(
                "启动时自动加载磁盘数据",
                dom_count == 2,
                f"DOM 项数={dom_count}（期望 2，说明启动未读到磁盘）",
            )
            title = window.evaluate_js(
                "var t=document.querySelector('.todo-title'); t ? t.textContent : ''"
            )
            check("加载的标题正确", title == "预置任务甲", f"title={title!r}")
            empty_hidden = window.evaluate_js(
                "document.getElementById('emptyState').hidden"
            )
            check("有数据时不显示空状态", empty_hidden is True, f"hidden={empty_hidden}")

            # 3) 通过 JS 调用 Python API 保存
            payload = json.dumps(
                [
                    {"id": "i1", "title": "集成测试项A", "priority": "high", "due": "", "done": False},
                    {"id": "i2", "title": "集成测试项B", "priority": "low", "due": "", "done": True},
                ],
                ensure_ascii=False,
            )
            window.evaluate_js(f"window.pywebview.api.save_todos({json.dumps(payload)})")
            time.sleep(1.5)

            on_disk = store.load()
            check(
                "Python 端收到前端保存的数据",
                len(on_disk) == 2 and on_disk[0]["title"] == "集成测试项A",
                f"读到 {len(on_disk)} 条",
            )
            check("数据文件内容正确", json.loads(DATA_FILE.read_text("utf-8"))[1]["done"] is True)

            # 4) 前端真实交互：输入框添加 → 自动持久化
            window.evaluate_js(
                "document.getElementById('inputText').value = '由集成测试添加';"
                "document.getElementById('addBtn').click();"
            )
            time.sleep(1.5)
            after = store.load()
            check(
                "前端交互新增已持久化",
                any(t.get("title") == "由集成测试添加" for t in after),
                f"共 {len(after)} 条",
            )

            # 5) 重启模拟：写入新数据 → 重新 boot → 应从磁盘读到最新
            store.save(
                [{"id": "z1", "title": "重启后的数据", "priority": "medium", "due": "", "done": False}]
            )
            window.evaluate_js("window.__todoApp.boot()")
            time.sleep(2.0)
            rebooted = window.evaluate_js(
                "var t=document.querySelector('.todo-title'); t ? t.textContent : ''"
            )
            check("重新加载读到最新磁盘数据", rebooted == "重启后的数据", f"title={rebooted!r}")

        except Exception as exc:  # noqa: BLE001
            check("集成测试执行", False, repr(exc))
        finally:
            try:
                window.destroy()
            except Exception:
                pass

    t = threading.Thread(target=run_js, daemon=True)
    t.start()

    webview.start()

    t.join(timeout=20)

    print("\n===== 集成测试结果 =====")
    for r in RESULTS:
        print(r)
    failed = [r for r in RESULTS if r.startswith("FAIL")]
    print(f"\n通过 {len(RESULTS) - len(failed)} / {len(RESULTS)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
