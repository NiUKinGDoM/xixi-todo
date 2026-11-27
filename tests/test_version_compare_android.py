"""验证手机版四段式版本比较规则（与 Kotlin UpdateChecker.compare 一致）。

Kotlin 源码里 compare 逐段 toIntOrNull() 比较；这里用同一规则复刻并断言，
同时校验 version-android.json 的版本与手机 build.gradle vc 一致。
"""
import json
import pathlib
import re
import sys

GLASS = pathlib.Path(__file__).resolve().parent.parent
ANDROID = GLASS.parent / "todo-android"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def compare(a, b):
    def parts(v):
        out = []
        for seg in str(v or "").strip().removeprefix("v").split("."):
            try:
                out.append(int(seg))
            except ValueError:
                out.append(0)
        return out
    pa, pb = parts(a), parts(b)
    for i in range(max(len(pa), len(pb))):
        x = pa[i] if i < len(pa) else 0
        y = pb[i] if i < len(pb) else 0
        if x != y:
            return x - y
    return 0


cases = [
    ("1.0.0.9", "1.0.0.10", -1),
    ("1.0.0.10", "1.0.0.9", 1),
    ("1.0.0.9", "1.0.0.9", 0),
    ("v1.0.1.0", "1.0.0.10", 1),
    ("1.1.0.0", "1.0.10.10", 1),
    ("1.0.0.10", "1.0.0.11", -1),
]
for a, b, sign in cases:
    r = compare(a, b)
    ok = (r > 0 and sign > 0) or (r < 0 and sign < 0) or (r == 0 and sign == 0)
    check(f"比较 {a} vs {b}", ok, f"got={r}")

# 版本一致性
va = json.loads((GLASS / "version-android.json").read_text(encoding="utf-8"))
gradle = (ANDROID / "app/build.gradle.kts").read_text(encoding="utf-8")
m = re.search(r"val vc = (\d+)", gradle)
vc = int(m.group(1)) if m else -1
expect = f"1.{(vc // 121) % 11}.{(vc // 11) % 11}.{vc % 11}"
check("version-android 与 vc 一致", va["version"] == expect, f"{va['version']} vs {expect}(vc={vc})")
check("versionCode 一致", va.get("versionCode") == vc, f"{va.get('versionCode')} vs {vc}")

# 更新日志从第一版起
kt = (ANDROID / "app/src/main/java/com/xixi/todo/nativeapp/ui/Changelog.kt").read_text(encoding="utf-8")
check("含 v1.0.0.1", "v1.0.0.1" in kt)
check("含当前版本", f"v{expect}" in kt, f"v{expect}")
check("版本条目数>=10", kt.count("VersionNote(") >= 10, str(kt.count("VersionNote(")))

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + detail) if detail else ""))
print()
print(f"{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
