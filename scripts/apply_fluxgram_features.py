#!/usr/bin/env python3
"""
FluxGram: встраивает в исходники DrKLO/Telegram
  * режим призрака (перехват запросов в ConnectionsManager)
  * экраны настроек FluxGram -> Режим призрака
  * пункт "FluxGram" в настройках Telegram
  * переименование Telegram -> FluxGram в серверных языковых пакетах
  * пакет приложения org.fluxgram.product

Использование: apply_fluxgram_features.py <telegram_dir> <overlay_dir>
Каждый патч ищет якорь в коде; если якорь не найден - пишет WARN/FAIL, а не молча пропускает.
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

    # у debug-сборки Telegram есть суффикс .beta -> убираем, чтобы пакет был ровно org.fluxgram.product
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
        params = m.group("rest").count(",") + 2  # + первый параметр TLObject
        if params < 6:  # короткие перегрузки только делегируют в полную
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


# ----------------------------------------------------------------------------- 4. entry in Telegram settings
def patch_settings_entry():
    done = False
    for name in ("ProfileActivity.java", "SettingsActivity.java"):
        path = f"{JAVA}/org/telegram/ui/{name}"
        if not os.path.exists(path):
            continue
        txt = read(path)
        if "fluxRow" in txt:
            report(f"Пункт FluxGram в {name}", True, False, "(уже применён)")
            done = True
            break
        if not re.search(r"\bnotificationRow\b", txt):
            continue

        # a) поле fluxRow
        cm = re.search(r"(public\s+class\s+\w+\s+extends\s+[^{]*\{)", txt)
        if not cm:
            continue
        txt = txt[:cm.end()] + "\n    private int fluxRow = -1;" + txt[cm.end():]

        # b) выдача номера строки + сброс
        if "notificationRow = rowCount++;" not in txt:
            report(f"Пункт FluxGram в {name}", False, False, "(нет 'notificationRow = rowCount++;')")
            continue
        txt = txt.replace("notificationRow = rowCount++;",
                          "fluxRow = rowCount++;\n            notificationRow = rowCount++;", 1)
        txt = re.sub(r"(\n[ \t]*)notificationRow\s*=\s*-1;", r"\1fluxRow = -1;\1notificationRow = -1;", txt, count=1)

        # c) тип строки / enabled: добавляем fluxRow во все цепочки "x == notificationRow ||"
        txt = re.sub(r"(\w+)\s*==\s*notificationRow\s*\|\|", r"\1 == fluxRow || \1 == notificationRow ||", txt)

        # d) клик и отрисовка
        found = {"click": 0, "bind": 0}

        def repl(m):
            tail = txt_after(m.end())
            i_icon = tail.find("setTextAndIcon(")
            i_pres = tail.find("presentFragment(")
            icon = i_icon if i_icon >= 0 else 10 ** 9
            pres = i_pres if i_pres >= 0 else 10 ** 9
            if icon < pres:
                vm = re.search(r"(\w+)\.setTextAndIcon\(", tail)
                var = vm.group(1) if vm else "textCell"
                found["bind"] += 1
                return (f"if (position == fluxRow) {{ {var}.setTextAndIcon(\"FluxGram\", R.drawable.flux_ghost, true); }} "
                        f"else if (position == notificationRow) {{")
            if pres < icon:
                found["click"] += 1
                return ("if (position == fluxRow) { presentFragment(new FluxGramSettingsActivity()); } "
                        "else if (position == notificationRow) {")
            return m.group(0)

        def txt_after(idx):
            return txt[idx: idx + 400]

        pat = re.compile(r"if\s*\(\s*position\s*==\s*notificationRow\s*\)\s*\{")
        # правим с конца, чтобы не сбить индексы
        out = txt
        for m in reversed(list(pat.finditer(txt))):
            new_piece = repl(m)
            out = out[:m.start()] + new_piece + out[m.end():]
        txt = out
        write(path, txt)
        ok = found["click"] >= 1 and found["bind"] >= 1
        report(f"Пункт FluxGram в {name}", ok, False,
               f"(клик: {found['click']}, отрисовка: {found['bind']})")
        done = ok
        break

    if done:
        return

    # fallback: пункт в боковом меню (drawer)
    ok1 = ok2 = False
    p1 = f"{JAVA}/org/telegram/ui/Adapters/DrawerLayoutAdapter.java"
    p2 = f"{JAVA}/org/telegram/ui/LaunchActivity.java"
    if os.path.exists(p1):
        t = read(p1)
        m = re.search(r"items\.add\(new Item\(8,", t)
        if m and "9777" not in t:
            t = t[:m.start()] + 'items.add(new Item(9777, "FluxGram", R.drawable.flux_ghost));\n        ' + t[m.start():]
            write(p1, t)
            ok1 = True
    if os.path.exists(p2):
        t = read(p2)
        m = re.search(r"int\s+id\s*=\s*drawerLayoutAdapter\.getId\(position\);", t)
        if m and "9777" not in t:
            t = (t[:m.end()]
                 + "\n                if (id == 9777) { presentFragment(new FluxGramSettingsActivity()); "
                   "drawerLayoutContainer.closeDrawer(false); return; }"
                 + t[m.end():])
            write(p2, t)
            ok2 = True
    report("Пункт FluxGram в боковом меню (запасной вариант)", ok1 and ok2, True,
           "(в настройках якорь не найден, добавлено в боковое меню)" if ok1 and ok2 else
           "(не удалось добавить ни в настройки, ни в боковое меню)")


# ----------------------------------------------------------------------------- 5. language pack rename
def patch_locale_controller():
    path = f"{JAVA}/org/telegram/messenger/LocaleController.java"
    if not os.path.exists(path):
        report("LocaleController (Telegram -> FluxGram в языковых пакетах)", False, False, "(файл не найден)")
        return
    txt = read(path)
    if "FluxBrand.apply" in txt:
        report("LocaleController (Telegram -> FluxGram в языковых пакетах)", True, False, "(уже применён)")
        return
    pat = re.compile(r"private\s+String\s+getStringInternal\s*\(([^)]*)\)\s*\{")
    defs = list(pat.finditer(txt))
    if not defs:
        report("LocaleController (Telegram -> FluxGram в языковых пакетах)", False, False,
               "(не найден getStringInternal; в русском интерфейсе может остаться 'Telegram')")
        return
    out = txt
    for m in reversed(defs):
        params = [p.strip() for p in m.group(1).split(",") if p.strip()]
        names = [p.split()[-1] for p in params]
        key = names[0]
        wrapper = (f"private String getStringInternal({m.group(1)}) {{\n"
                   f"        return org.telegram.messenger.fork.FluxBrand.apply({key}, getStringInternalOrig({', '.join(names)}));\n"
                   f"    }}\n\n    ")
        renamed = f"private String getStringInternalOrig({m.group(1)}) {{"
        out = out[:m.start()] + wrapper + renamed + out[m.end():]
    write(path, out)
    report("LocaleController (Telegram -> FluxGram в языковых пакетах)", True, False, f"({len(defs)} перегрузок)")


# ----------------------------------------------------------------------------- 6. hardcoded titles
def patch_hardcoded_titles():
    changed = []
    for rel in ("org/telegram/ui/DialogsActivity.java", "org/telegram/ui/Stories/DialogStoriesCell.java"):
        path = f"{JAVA}/{rel}"
        if not os.path.exists(path):
            continue
        txt = read(path)
        new = re.sub(r'setTitle\(\s*"Telegram( Beta)?"', lambda m: f'setTitle("FluxGram{m.group(1) or ""}"', txt)
        if new != txt:
            write(path, new)
            changed.append(rel)
        for i, line in enumerate(read(path).splitlines(), 1):
            if '"Telegram' in line:
                print(f"        литерал в {rel}:{i}: {line.strip()}")
    report("Жёстко заданные заголовки 'Telegram'", True, False, f"(изменено: {', '.join(changed) or 'ничего'})")


def main():
    print(f"=== FluxGram features -> {TG} ===")
    patch_package()
    copy_overlay()
    patch_connections_manager()
    patch_send_messages_helper()
    patch_settings_entry()
    patch_locale_controller()
    patch_hardcoded_titles()
    failed = [n for n, ok, req in results if not ok and req]
    warned = [n for n, ok, req in results if not ok and not req]
    print("\n=== Итог ===")
    print("Критичные ошибки:", failed or "нет")
    print("Предупреждения:  ", warned or "нет")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
