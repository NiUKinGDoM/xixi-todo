"""桌面版 ↔ 手机端 业务逻辑对齐测试。

两端是两份独立实现（JS / Kotlin），历史上出现过多处行为不一致。
本测试从两端源码读出关键规则，断言它们已对齐；并对快速语法的
golden 用例验证解析规则覆盖完整（用例取自 tests/smoke.js）。

只做静态校验，不联网、不碰用户数据。
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JS = ROOT / "ui/app.js"
KT_APP = ROOT.parent / "todo-android/app/src/main/java/com/xixi/todo/nativeapp/ui/TodoApp.kt"
KT_SCREEN = ROOT.parent / "todo-android/app/src/main/java/com/xixi/todo/nativeapp/ui/TodoScreens.kt"
KT_STORE = ROOT.parent / "todo-android/app/src/main/java/com/xixi/todo/nativeapp/data/TodoStore.kt"
KT_QUICK = ROOT.parent / "todo-android/app/src/main/java/com/xixi/todo/nativeapp/data/QuickInput.kt"
KT_DIALOG = ROOT.parent / "todo-android/app/src/main/java/com/xixi/todo/nativeapp/ui/TodoDialogs.kt"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(p):
    return p.read_text(encoding="utf-8") if p.exists() else ""


js = read(JS)
kta = read(KT_APP)
kts = read(KT_SCREEN)
kstore = read(KT_STORE)
kquick = read(KT_QUICK)
kdlg = read(KT_DIALOG)

# 1) 快速语法解析：桌面有、手机必须也接入
check("手机有 QuickInput 解析", "object QuickInput" in kquick and "fun parse(" in kquick)
check("手机 AddDialog 调用解析", "QuickInput.parse(text)" in kdlg)
check("解析值优先表单兜底", "q.priority.ifBlank" in kdlg and "q.due.ifBlank" in kdlg)
# 桌面 golden 覆盖的语法，手机 QuickInput 源码里必须都有对应规则
for token, rule in [
    ("!高优先级", "[高中低hml]"),
    ("每天", "每天|每日"),
    ("工作日", "每个?工作日"),
    ("每周", "每周|每星期"),
    ("每月", "每月"),
    ("每年", "每年"),
    ("大后天", "大后天"),
    ("后天", "后天"),
    ("明天", "明(?:天|日|儿)"),
    ("今天", "今(?:天|日|儿)"),
    ("下周X", "(?:周|星期)"),
    ("M月D日", "月"),
    ("冒号时间", "[:：]"),
    ("N点", "点"),
    ("点半", "半"),
]:
    check(f"语法覆盖: {token}", rule in kquick, rule)


# 1b) 中文数字时间识别（用户：「明天八点开会」）
check("手机有中文数字转换 cnToInt", "fun cnToInt" in kquick)
check("手机中文时间正则", "{1,3})点" in kquick)
check("手机中文点半", 'rest == "半"' in kquick)

# 2) 重复任务追赶今天
check("桌面 nextDueDate 追赶", "function nextDueDate" in js and "Math.ceil" in js)
check("手机 advanceRepeat 追赶", "isBefore(today)" in kstore and "ChronoUnit" in kstore)
check("手机有 guard 上限", "guard < 3000" in kstore)

# 3) 日期解析严格化（两端都是 yyyy-MM-dd 严格）
check("桌面 DATE_RE 严格", r"/^\d{4}-\d{2}-\d{2}$/" in js)
check("手机 normalizeDate 严格", r"\d{4}-\d{2}-\d{2}" in kstore and "s.length != 10" in kstore)

# 4) 排序三档 + order
check("桌面优先级三档", "high: 0, medium: 1, low: 2" in js.replace("'", '"'))
check("手机优先级三档", 'mapOf("high" to 0, "medium" to 1, "low" to 2)' in kta)
check("手机排序含 order", "it.order ?: Int.MAX_VALUE" in kta)

# 5) 进度取整 round
check("桌面 Math.round 进度", "Math.round" in js and "sDone / sTotal" in js)
check("手机 round 进度", "kotlin.math.round(" in kts)

# 6) 顶栏计数含置顶
check("桌面计数含置顶", "!x.done" in js)
check("手机计数含置顶", 'count = todos.count { !it.done }' in kta)

# 7) 清空 n=0 提示
check("桌面清空 n=0 提示", "没有已完成的待办" in js)
check("手机清空 n=0 提示", "没有已完成的待办" in kta)

# 8) 今天筛选口径一致（都不含逾期、不含完成）
check("桌面今天筛选", "x.due === t" in js and "!x.done && x.due === t" in js)
check("手机今天筛选", 'it.due == today' in kta and '!it.done' in kta)

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + detail) if detail else ""))
print()
print(f"{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
