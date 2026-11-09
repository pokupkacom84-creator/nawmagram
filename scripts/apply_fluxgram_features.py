#!/usr/bin/env python3
"""
FluxGram: встраивает в исходники DrKLO/Telegram
  * режим призрака (перехват запросов в ConnectionsManager)
  * экраны настроек FluxGram -> Режим призрака
  * строка "FluxGram" в настройках Telegram
  * переименование Telegram -> FluxGram в серверных языковых пакетах
  * пакет приложения org.fluxgram.product

Использование: apply_fluxgram_features.py <telegram_dir> <overlay_dir>
"""
import os
import re
import shutil
import sys

TG = sys.argv[1] if len(sys.argv) > 1 else "telegram"
OVERLAY = sys.argv[2] if len(sys.argv) > 2 else "overlay/overlay"

APP_PACKAGE = "org.fluxgram.product"
JAVA = f"{TG}/TMessagesProj/src/main/java"
RES = f"{TG}/TMessagesProj/src/main/res"

results = []  # (name, status, required)


def report(name, ok, required, detail=""):
    status = "OK  " if ok else ("FAIL" if required else "WARN")
    results.append((name, ok, required))
    print(f"[{status}] {name} {detail}")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ----------------------------------------------------------------------------- 0. package name
def patch_package():
    ok = False
    gp = f"{TG}/gradle.properties"
    if os.path.exists(gp):
        txt = read(gp)
        if re.search(r"^APP_PACKAGE=.*$", txt, flags=re.M):
            txt = re.sub(r"^APP_PACKAGE=.*$", f"APP_PACKAGE={APP_PACKAGE}", txt, flags=re.M)
        else:
            txt += f"\nAPP_PACKAGE={APP_PACKAGE}\n"
        write(gp, txt)
        ok = True
    report("gradle.properties APP_PACKAGE", ok, True, f"-> {APP_PACKAGE}")

    bg = f"{TG}/TMessagesProj_App/build.gradle"
    if os.path.exists(bg):
        txt = read(bg)
        new = re.sub(r"^[ \t]*applicationIdSuffix\s+[\"']\.beta[\"'][ \t]*\n", "", txt, flags=re.M)
        if new != txt:
            write(bg, new)
            report("build.gradle: убран applicationIdSuffix .beta", True, False)
        else:
            report("build.gradle: applicationIdSuffix .beta не найден (возможно, уже убран)", True, False)
        for m in re.finditer(r"^.*applicationId.*$", read(bg), flags=re.M):
            print("       ", m.group(0).strip())


# ----------------------------------------------------------------------------- 1. copy overlay files
def copy_overlay():
    count = 0
    src_java = f"{OVERLAY}/java"
    for root, _, files in os.walk(src_java):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), src_java)
            dst = os.path.join(JAVA, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(root, fn), dst)
            count += 1
    icon_src = f"{OVERLAY}/res/drawable/flux_ghost.xml"
    if os.path.exists(icon_src):
        os.makedirs(f"{RES}/drawable", exist_ok=True)
        shutil.copyfile(icon_src, f"{RES}/drawable/flux_ghost.xml")
        count += 1
    report("копирование файлов FluxGram", count >= 6, True, f"({count} файлов)")


# ----------------------------------------------------------------------------- 2. ConnectionsManager hook
SEND_RE = re.compile(
    r"(?P<head>(?:public|private|protected)\s+(?:static\s+)?(?P<ret>int|void)\s+(?P<name>sendRequest\w*)"
    r"\s*\(\s*(?:final\s+)?TLObject\s+(?P<obj>\w+)\s*,(?P<rest>[^)]*)\)\s*(?:throws\s+[\w., ]+)?\{)"
)


def patch_connections_manager():
    path = f"{JAVA}/org/telegram/tgnet/ConnectionsManager.java"
    if not os.path.exists(path):
        report("ConnectionsManager hook", False, True, "(файл не найден)")
        return
    txt = read(path)
    if "FluxGhost.intercept" in txt:
        report("ConnectionsManager hook", True, True, "(уже применён)")
        return
    patched = []

    def repl(m):
        params = m.group("rest").count(",") + 2
        if params < 6:
            return m.group(0)
        ret = " 0" if m.group("ret") == "int" else ""
        patched.append(m.group("name"))
        return (m.group("head")
                + f"\n        if (org.telegram.messenger.fork.FluxGhost.intercept(currentAccount, {m.group('obj')})) {{ return{ret}; }}")

    new = SEND_RE.sub(repl, txt)
    if patched:
        write(path, new)
    report("ConnectionsManager hook", bool(patched), True, f"(методы: {', '.join(patched)})" if patched else
           "(не найден метод sendRequest(TLObject, ..., boolean immediate))")


# ----------------------------------------------------------------------------- 3. SendMessagesHelper ("use scheduling")
def patch_send_messages_helper():
    path = f"{JAVA}/org/telegram/messenger/SendMessagesHelper.java"
    if not os.path.exists(path):
        report("SendMessagesHelper hook (Использовать отложку)", False, False, "(файл не найден)")
        return
    txt = read(path)
    if "FluxGhost.onSendParams" in txt:
        report("SendMessagesHelper hook (Использовать отложку)", True, False, "(уже применён)")
        return
    pat = re.compile(r"(public\s+void\s+sendMessage\s*\(\s*SendMessageParams\s+(\w+)\s*\)\s*\{)")
    m = pat.search(txt)
    if not m:
        report("SendMessagesHelper hook (Использовать отложку)", False, False,
               "(не найден sendMessage(SendMessageParams); опция 'Использовать отложку' работать не будет)")
        return
    ins = f"{m.group(1)}\n        org.telegram.messenger.fork.FluxGhost.onSendParams({m.group(2)}, currentAccount);"
    write(path, txt[:m.start()] + ins + txt[m.end():])
    report("SendMessagesHelper hook (Использовать отложку)", True, False)


# -------------------------
