"""桌面版 ↔ 手机端 WebDAV 同步决策对照测试。

背景：两端各自实现「谁新以谁为准」，历史上行为相反 ——
  · 桌面 app.py sync_pull: `if remote_ts and remote_ts <= local_ts and exists` → 本地新
  · 手机 TodoApp.kt:        `remote.updatedAt > 0 && remote <= localTs && localExists` → 本地新
本测试把两条判定用同一批用例跑，断言结果一致，防止以后改歪。

同时直接从源码读出两边的表达式做文本校验，确保实现没被改回旧写法。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
KT_APP = ROOT.parent / "todo-android/app/src/main/java/com/xixi/todo/nativeapp/ui/TodoApp.kt"
KT_DIALOG = ROOT.parent / "todo-android/app/src/main/java/com/xixi/todo/nativeapp/ui/TodoDialogs.kt"
KT_STORE = ROOT.parent / "todo-android/app/src/main/java/com/xixi/todo/nativeapp/data/TodoStore.kt"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


# ---- 1. 判定逻辑对照（同一批输入，两端结果必须一致） ----
def desktop_local_is_newer(remote_ts, local_ts, local_exists):
    # 照抄 app.py:1015  `if remote_ts and remote_ts <= local_ts and self.store.path.exists()`
    return bool(remote_ts) and remote_ts <= local_ts and local_exists


def android_local_is_newer(remote_ts, local_ts, local_exists):
    # 照抄 TodoApp.kt / TodoDialogs.kt  `remote.updatedAt > 0L && ... && localExists`
    return remote_ts > 0 and remote_ts <= local_ts and local_exists


cases = [
    # (remote_ts, local_ts, local_exists, 说明)
    (2000, 1000, True, "云端更新 → 都用云端"),
    (1000, 2000, True, "本地更新 → 都反推"),
    (1000, 1000, True, "时间戳相同 → 都反推(<=)"),
    (0, 2000, True, "云端无meta → 都用云端(关键:以前两端相反)"),
    (0, 0, True, "都无meta → 都用云端"),
    (2000, 1000, False, "本地文件不存在 → 都用云端"),
    (0, 5000, False, "无meta+无本地文件 → 都用云端"),
]
for r, l, ex, desc in cases:
    d = desktop_local_is_newer(r, l, ex)
    a = android_local_is_newer(r, l, ex)
    check(f"判定一致: {desc}", d == a, f"desktop={d} android={a}")

# ---- 2. meta 时间戳写法规矩 ----
# 覆盖云端时：remote_ts or now —— 两端都不能在无 meta 时写 0
def desktop_meta_on_cover(remote_ts, now):
    return remote_ts or now


def android_meta_on_cover(remote_ts, now):
    return remote_ts if remote_ts > 0 else now

for r in (0, 999):
    check(f"覆盖后meta: remote={r}", desktop_meta_on_cover(r, 12345) == android_meta_on_cover(r, 12345))

# ---- 3. 源码文本校验：防止实现被改回旧写法 ----
app_src = APP.read_text(encoding="utf-8") if APP.exists() else ""
kt_app_src = KT_APP.read_text(encoding="utf-8") if KT_APP.exists() else ""
kt_dlg_src = KT_DIALOG.read_text(encoding="utf-8") if KT_DIALOG.exists() else ""
kt_store_src = KT_STORE.read_text(encoding="utf-8") if KT_STORE.exists() else ""

check("桌面仍是 remote_ts and <= local_ts",
      "remote_ts and remote_ts <= local_ts" in app_src)
check("手机启动同步用 > 0 守卫",
      "remote.updatedAt > 0L && remote.updatedAt <= localTs" in kt_app_src)
check("手机设置页下载强制覆盖(时间戳仅取 ts)",
      "val ts = if (pull.updatedAt > 0L) pull.updatedAt else System.currentTimeMillis()" in kt_dlg_src)
check("手机覆盖前备份", "backupBeforeOverwrite" in kt_app_src and "backupBeforeOverwrite" in kt_dlg_src)
check("手机有 backupBeforeOverwrite 实现", "fun backupBeforeOverwrite" in kt_store_src)
check("手机上传成功才写meta（启动同步）", "if (r.first) TodoStore.writeMeta(ctx, now)" in kt_app_src)
check("手机上传成功才写meta（设置页）", "if (r.first) withContext(Dispatchers.IO) { TodoStore.writeMeta(ctx, now) }" in kt_dlg_src)


# 手动下载强制覆盖（两端一致）
check("桌面 sync_pull 支持 force", "def sync_pull(self, force" in app_src)
check("桌面 force 跳过反推", "if not force_download and (" in app_src and "local_unknown" in app_src)
check("桌面前端下载传 force", "callApi('sync_pull', '1')" in (ROOT / 'ui/app.js').read_text(encoding='utf-8'))
check("手机下载强制覆盖(无反推)", "localIsNewer" not in kt_dlg_src)


# 本地有数据但 meta=0 的保护（两端一致：判本地新，防云端空数据覆盖）
check("桌面保护本地无meta数据", "local_unknown" in app_src and "local_has_data" in app_src)
check("手机保护本地无meta数据", "localUnprotected" in kt_app_src and "localHasData" in kt_app_src)

bad = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + detail) if detail else ""))
print()
print(f"{len(results) - len(bad)}/{len(results)} 通过")
sys.exit(1 if bad else 0)
