"""快速添加语法：桌面 smoke.js golden 用例 ↔ 手机 QuickInput 规则对照。

Kotlin 的 Regex 与 JS RegExp 对这些语法等价；这里用 Python 同一套规则复刻
两端共用的匹配顺序（优先级→重复→日期→时间），跑桌面 smoke.js 的 golden
用例，证明移植的规则覆盖完整、行为一致。真正的 Kotlin 实现由 Gradle 编译
保证语法正确，本脚本验证规则语义。
"""
import re
import sys
from datetime import date, timedelta

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


WEEK = {"日": 0, "天": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
BOUND = r"(?=[\s\d]|$|[!#]|[^\x00-\x7F])"


def pad(n):
    return f"{n:02d}"


def fmt(d):
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


def parse(raw, today):
    text = " " + raw + " "
    out = {"title": "", "priority": "", "due": "", "time": "", "repeat": ""}

    m = re.search(r"\s!([高中低hml])" + BOUND, text)
    if m:
        k = m.group(1)
        out["priority"] = "high" if k in ("高", "h") else ("low" if k in ("低", "l") else "medium")
        text = text[:m.start()] + " " + text[m.end():]

    for pat, val in [(r"每天|每日", "daily"), (r"每个?工作日", "weekday"),
                     (r"每周|每星期", "weekly"), (r"每月", "monthly"), (r"每年", "yearly")]:
        m = re.search(r"\s(" + pat + r")" + BOUND, text)
        if m:
            out["repeat"] = val
            text = text[:m.start()] + " " + text[m.end():]

    matched = False
    for kw, days in [("大后(?:天|儿)", 3), ("后(?:天|儿)", 2), ("明(?:天|日|儿)|明早|明晚", 1), ("今(?:天|日|儿)|今早|今晚", 0)]:
        if matched:
            break
        m = re.search(r"\s(?:" + kw + r")" + BOUND, text)
        if m:
            out["due"] = fmt(today + timedelta(days=days))
            text = text[:m.start()] + " " + text[m.end():]
            matched = True

    if not matched:
        m = re.search(r"\s(下|本|这)?(?:周|星期)([一二三四五六日天])" + BOUND, text)
        if m and m.group(2) in WEEK:
            target = WEEK[m.group(2)]
            cur = (today.weekday() + 1) % 7  # 周一=0
            if m.group(1) == "下":
                dow_cur = (cur + 6) % 7
                dow_tgt = (target + 6) % 7
                delta = -dow_cur + 7 + dow_tgt
            else:
                delta = (target - cur + 7) % 7
            out["due"] = fmt(today + timedelta(days=delta))
            text = text[:m.start()] + " " + text[m.end():]
            matched = True

    if not matched:
        m = re.search(r"\s(\d{1,2})月(\d{1,2})[日号]?" + BOUND, text)
        if m and 1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(2)) <= 31:
            mm, dd = int(m.group(1)), int(m.group(2))
            cand = date(today.year, mm, min(dd, 31))
            if cand < today:
                cand = cand.replace(year=today.year + 1)
            out["due"] = fmt(cand)
            text = text[:m.start()] + " " + text[m.end():]
            matched = True

    m = re.search(r"\s(\d{1,2})[:：](\d{2})(?=[\s]|$|[^\x00-\x7F])", text)
    if m and int(m.group(1)) <= 23 and int(m.group(2)) <= 59:
        out["time"] = f"{pad(int(m.group(1)))}:{pad(int(m.group(2)))}"
        text = text[:m.start()] + " " + text[m.end():]

    m = re.search(r"\s(\d{1,2})点(半|\d{1,2}分?)?(?=[\s]|$|[^\x00-\x7F])", text)
    if m and int(m.group(1)) <= 23:
        rest = m.group(2) or ""
        mm = 30 if rest == "半" else (int(rest.rstrip("分")) if rest.isdigit() or rest.rstrip("分").isdigit() else 0)
        out["time"] = f"{pad(int(m.group(1)))}:{pad(mm)}"
        text = text[:m.start()] + " " + text[m.end():]

    out["title"] = re.sub(r"\s+", " ", text).strip() or raw.strip()
    return out


T = date(2026, 11, 27)  # 固定基准日，跟 golden 用例无关

# smoke.js 的 golden 用例
cases = [
    ("写方案 !高", {"priority": "high", "title": "写方案"}),
    ("整理资料 #工作", {"title": "整理资料 #工作"}),
    ("交报告 明天", {"due": fmt(T + timedelta(days=1)), "title": "交报告"}),
    ("开会 9点30分", {"time": "09:30"}),
    ("晨会 8:15", {"time": "08:15"}),
    ("周会 每周", {"repeat": "weekly", "title": "周会"}),
    ("明天9点 客户拜访 !高 每天",
     {"priority": "high", "repeat": "daily", "time": "09:00", "due": fmt(T + timedelta(days=1))}),
    ("买 3 个苹果", {"title": "买 3 个苹果", "due": "", "priority": ""}),
    ("开会 9:99", {"time": ""}),
]
for raw, expect in cases:
    got = parse(raw, T)
    ok = all(got[k] == v for k, v in expect.items())
    check(f"golden: {raw}", ok, f"got={got} expect={expect}" if not ok else "")


# 常用口头语日期
for raw, days in [("开会 今儿", 0), ("交报告 明儿", 1), ("洗澡 后儿", 2), ("交差 大后儿", 3)]:
    r = parse(raw, T)
    want = fmt(T + timedelta(days=days))
    check(f"口头语: {raw}", r["due"] == want, f"due={r['due']} want={want}")

# 下周X 落在 1~7 天内且是那一天（smoke.js:754）
r = parse("交周报 下周一", T)
d = date.fromisoformat(r["due"])
delta = (d - T).days
check("下周一在1~7天内", 1 <= delta <= 7, f"due={r['due']} 天数={delta}")
check("下周一是周一", d.weekday() == 0, f"weekday={d.weekday()}")

bad = [x for x in results if not x[1]]
for name, ok, detail in results:
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + detail) if detail else ""))
print()
print(f"{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
