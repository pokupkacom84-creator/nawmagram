#!/usr/bin/env python3
"""
FluxGram: добавляет отдельный пункт «FluxGram» (-> Режим призрака) в главный экран настроек Telegram.

Запуск:  patch_fluxgram_settings_entry.py <telegram_dir>
Запускать ПОСЛЕ apply_fluxgram_features.py (файлы FluxGramSettingsActivity / flux_ghost.xml уже скопированы).

В отличие от старого патча, якорь не один (notificationRow), а список: в новом дизайне настроек
нужной строки может не быть. Скрипт берёт первую найденную строку из списка, вставляет fluxRow
перед ней и правит клик / отрисовку / isEnabled. Если что-то не нашлось — честно пишет FAIL
и печатает кусок кода, который нужно прислать, чтобы доделать вручную.
"""
import os
import re
import sys

TG = sys.argv[1] if len(sys.argv) > 1 else "telegram"
UI = f"{TG}/TMessagesProj/src/main/java/org/telegram/ui"

# порядок = приоритет (чем выше строка на экране, тем лучше)
ANCHORS = ["accountRow", "chatRow", "privacyRow", "notificationRow", "dataRow",
           "foldersRow", "devicesRow", "powerUsageRow", "languageRow"]
FILES = ["SettingsActivity.java", "ProfileActivity.java"]


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, t):
    with open(p, "w", encoding="utf-8") as f:
        f.write(t)


def fail(msg, ctx=None):
    print(f"[FAIL] {msg}")
    if ctx:
        print("------ пришлите этот фрагмент ------")
        print(ctx)
        print("------------------------------------")
    sys.exit(1)


def find_target():
    for name in FILES:
        p = f"{UI}/{name}"
        if not os.path.exists(p):
            continue
        txt = read(p)
        if "fluxRow" in txt:
            print(f"[OK  ] {name}: пункт уже добавлен")
            sys.exit(0)
        found = [(txt.find(m.group(0)), a) for a in ANCHORS
                 for m in [re.search(rf"\b{a}\s*=\s*rowCount\+\+\s*;", txt)] if m]
        if found:
            found.sort()
            return p, name, txt, found[0][1]
    fail("не найден файл настроек с rowCount++ и известными строками (" + ", ".join(ANCHORS) + ")")


def main():
    path, name, txt, anchor = find_target()
    print(f"[....] файл {name}, якорь {anchor}")

    # a) поле
    cm = re.search(r"public\s+class\s+\w+\s+extends\s+[^{]*\{", txt)
    if not cm:
        fail("не найдено объявление класса")
    txt = txt[:cm.end()] + "\n    private int fluxRow = -1;" + txt[cm.end():]

    # b) выдача строки (перед якорем) и сброс
    txt, n = re.subn(rf"(\n[ \t]*)({anchor}\s*=\s*rowCount\+\+\s*;)",
                     r"\1fluxRow = rowCount++;\1\2", txt, count=1)
    if not n:
        fail("не удалось вставить fluxRow = rowCount++")
    txt = re.sub(rf"(\n[ \t]*){anchor}\s*=\s*-1\s*;", rf"\1fluxRow = -1;\1{anchor} = -1;", txt, count=1)

    # c) isEnabled / тип строки: «x == anchor ||» -> «x == fluxRow || x == anchor ||»
    txt = re.sub(rf"(\w+)\s*==\s*{anchor}\s*\|\|", rf"\1 == fluxRow || \1 == {anchor} ||", txt)

    # d) клик и отрисовка
    pat = re.compile(rf"if\s*\(\s*position\s*==\s*{anchor}\s*\)\s*\{{")
    click = bind = 0
    out = txt
    for m in reversed(list(pat.finditer(txt))):
        tail = txt[m.end(): m.end() + 500]
        i_icon = min([i for i in (tail.find("setTextAndIcon("), tail.find("Icon(")) if i >= 0] or [10 ** 9])
        i_pres = tail.find("presentFragment(")
        i_pres = i_pres if i_pres >= 0 else 10 ** 9
        if i_pres < i_icon:
            piece = ("if (position == fluxRow) { presentFragment(new FluxGramSettingsActivity()); } "
                     f"else if (position == {anchor}) {{")
            click += 1
        elif i_icon < i_pres:
            vm = re.search(r"(\w+)\.setTextAndIcon\(", tail)
            if not vm:
                continue
            piece = (f"if (position == fluxRow) {{ {vm.group(1)}.setTextAndIcon(\"FluxGram\", "
                     f"R.drawable.flux_ghost, true); }} else if (position == {anchor}) {{")
            bind += 1
        else:
            continue
        out = out[:m.start()] + piece + out[m.end():]
    write(path, out)

    print(f"[....] клик: {click}, отрисовка: {bind}")
    if click == 0 or bind == 0:
        ctx = "\n".join(l for l in out.splitlines() if anchor in l or "fluxRow" in l)
        fail(f"{name}: строка добавлена, но не найден "
             f"{'обработчик клика' if click == 0 else 'код отрисовки (setTextAndIcon)'} для {anchor}", ctx)
    print(f"[OK  ] пункт FluxGram добавлен в {name} перед {anchor}")


main()
