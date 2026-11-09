#!/usr/bin/env python3
"""
FluxGram: встраивает в исходники DrKLO/Telegram
  * режим призрака (перехват запросов в ConnectionsManager)
  * экраны настроек FluxGram -> Режим призрака
  * кнопка/пункт "FluxGram" в настройках Telegram
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


# ----------------------------------------------------------------------------- 4. entry in Telegram settings (запасные способы)
SETTINGS_FILES = ["SettingsActivity.java", "ProfileActivity.java"]
SETTINGS_ANCHORS = ["accountRow", "chatRow", "privacyRow", "notificationRow", "dataRow",
                    "foldersRow", "devicesRow", "powerUsageRow", "languageRow"]
MENU_ID = 9777


def _settings_rows(txt):
    found = []
    for a in SETTINGS_ANCHORS:
        m = re.search(rf"\b{a}\s*=\s*rowCount\+\+\s*;", txt)
        if m:
            found.append((m.start(), a))
    if not found:
        return None, "A: нет строк-якорей"
    anchor = sorted(found)[0][1]
    cm = re.search(r"public\s+class\s+\w+\s+extends\s+[^{]*\{", txt)
    if not cm:
        return None, "A: нет объявления класса"
    out = txt[:cm.end()] + "\n    private int fluxRow = -1;" + txt[cm.end():]
    out, n = re.subn(rf"(\n[ \t]*)({anchor}\s*=\s*rowCount\+\+\s*;)", r"\1fluxRow = rowCount++;\1\2", out, count=1)
    if not n:
        return None, "A: не вставилась fluxRow"
    out = re.sub(rf"(\n[ \t]*){anchor}\s*=\s*-1\s*;", rf"\1fluxRow = -1;\1{anchor} = -1;", out, count=1)
    out = re.sub(rf"(\w+)\s*==\s*{anchor}\s*\|\|", rf"\1 == fluxRow || \1 == {anchor} ||", out)

    pat = re.compile(rf"if\s*\(\s*position\s*==\s*{anchor}\s*\)\s*\{{")
    click = bind = 0
    res = out
    for m in reversed(list(pat.finditer(out))):
        tail = out[m.end(): m.end() + 500]
        vm = re.search(r"(\w+)\.setTextAndIcon\(", tail)
        i_icon = vm.start() if vm else 10 ** 9
        i_pres = tail.find("presentFragment(")
        i_pres = i_pres if i_pres >= 0 else 10 ** 9
        if i_pres < i_icon:
            piece = ("if (position == fluxRow) { presentFragment(new FluxGramSettingsActivity()); } "
                     f"else if (position == {anchor}) {{")
            click += 1
        elif vm:
            piece = (f"if (position == fluxRow) {{ {vm.group(1)}.setTextAndIcon(\"FluxGram\", "
                     f"R.drawable.flux_ghost, true); }} else if (position == {anchor}) {{")
            bind += 1
        else:
            continue
        res = res[:m.start()] + piece + res[m.end():]
    if click == 0 or bind == 0:
        return None, f"A: якорь {anchor}, но клик={click}, отрисовка={bind}"
    return res, f"строка в списке перед {anchor}"


def _settings_menu(txt):
    m = re.search(r"(?m)^([ \t]*)(\w+)\.addSubItem\(\s*\w+\s*,", txt)
    if not m:
        return None, "B: нет addSubItem"
    before = txt[:m.start()].rstrip()
    if not before or before[-1] not in ";{}":
        return None, "B: addSubItem без скобок после if/else, вставлять небезопасно"
    k = re.search(r"onItemClick\(\s*(?:final\s+)?int\s+(\w+)\s*\)\s*\{", txt)
    if not k:
        return None, "B: нет onItemClick(int id)"
    ind, var, idv = m.group(1), m.group(2), k.group(1)
    out = txt[:m.start()] + f'{ind}{var}.addSubItem({MENU_ID}, R.drawable.flux_ghost, "FluxGram");\n' + txt[m.start():]
    k = re.search(r"onItemClick\(\s*(?:final\s+)?int\s+(\w+)\s*\)\s*\{", out)
    out = (out[:k.end()]
           + f"\n                if ({idv} == {MENU_ID}) {{ presentFragment(new FluxGramSettingsActivity()); return; }}"
           + out[k.end():])
    return out, "пункт в меню ⋮"


def _settings_diagnostics(path, txt):
    print("------ ДИАГНОСТИКА: пришлите этот вывод ------")
    print("файл:", path)
    for i, l in enumerate(txt.splitlines(), 1):
        if re.search(r"Row\s*=\s*rowCount\+\+|addSubItem\(|UItem\.as|setTextAndIcon|PowerUsage|LanguageSettings|onItemClick|createView", l):
            print(f"{i}: {l.strip()[:160]}")
    print("----------------------------------------------")


def patch_settings_entry():
    name_ = "Пункт FluxGram в настройках"
    for name in SETTINGS_FILES:
        path = f"{JAVA}/org/telegram/ui/{name}"
        if not os.path.exists(path):
            continue
        txt = read(path)
        if "FluxGramSettingsActivity" in txt:
            report(name_, True, False, f"({name}: уже применён)")
            return
        notes = []
        for fn in (_settings_rows, _settings_menu):
            new, note = fn(txt)
            if new:
                write(path, new)
                report(name_, True, False, f"({name}: {note})")
                return
            notes.append(note)
        report(name_, False, False, f"({name}: " + "; ".join(notes) + ")")
        _settings_diagnostics(path, txt)
    patch_drawer_entry()


def patch_drawer_entry():
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
    report("Пункт FluxGram в боковом меню (запасной вариант)", ok1 and ok2, False,
           "(добавлено)" if ok1 and ok2 else "(не добавлено; сборка продолжится)")


# ----------------------------------------------------------------------------- 4b. кнопка FluxGram в шапке настроек (основной способ)
INJECTOR_JAVA = """package org.telegram.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.drawable.Drawable;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.widget.FrameLayout;

import androidx.core.content.ContextCompat;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.R;
import org.telegram.messenger.UserConfig;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.ActionBar.Theme;
import org.telegram.ui.Components.LayoutHelper;

public class FluxSettingsInjector {

    private static final String TAG_VIEW = "flux_settings_button";

    private static boolean isOwnProfile(BaseFragment fragment) {
        try {
            java.lang.reflect.Field f = fragment.getClass().getDeclaredField("userId");
            f.setAccessible(true);
            long id = ((Number) f.get(fragment)).longValue();
            return id == UserConfig.getInstance(UserConfig.selectedAccount).getClientUserId();
        } catch (Throwable t) {
            return false;
        }
    }

    public static void attach(final BaseFragment fragment, View root) {
        try {
            if (!(root instanceof FrameLayout)) {
                return;
            }
            if (fragment.getClass().getSimpleName().equals("ProfileActivity") && !isOwnProfile(fragment)) {
                return;
            }
            FrameLayout frame = (FrameLayout) root;
            for (int i = 0; i < frame.getChildCount(); i++) {
                if (TAG_VIEW.equals(frame.getChildAt(i).getTag())) {
                    return;
                }
            }
            Context context = frame.getContext();
            final Drawable icon = ContextCompat.getDrawable(context, R.drawable.flux_ghost).mutate();
            final Paint bg = new Paint(Paint.ANTI_ALIAS_FLAG);
            View button = new View(context) {
                private boolean pressed;

                @Override
                protected void onDraw(Canvas canvas) {
                    bg.setColor(Theme.getColor(Theme.key_windowBackgroundWhite));
                    bg.setAlpha(pressed ? 255 : 235);
                    float r = getWidth() / 2f;
                    canvas.drawCircle(r, r, r, bg);
                    icon.setTint(Theme.getColor(Theme.key_featuredStickers_addButton));
                    int s = AndroidUtilities.dp(24);
                    int l = (getWidth() - s) / 2;
                    int t = (getHeight() - s) / 2;
                    icon.setBounds(l, t, l + s, t + s);
                    icon.draw(canvas);
                }

                @Override
                public boolean onTouchEvent(MotionEvent e) {
                    switch (e.getAction()) {
                        case MotionEvent.ACTION_DOWN:
                            pressed = true;
                            invalidate();
                            return true;
                        case MotionEvent.ACTION_UP:
                            pressed = false;
                            invalidate();
                            performClick();
                            return true;
                        case MotionEvent.ACTION_CANCEL:
                            pressed = false;
                            invalidate();
                            return true;
                    }
                    return super.onTouchEvent(e);
                }
            };
            button.setTag(TAG_VIEW);
            button.setContentDescription("FluxGram");
            button.setOnClickListener(v -> fragment.presentFragment(new FluxGramSettingsActivity()));
            FrameLayout.LayoutParams lp = LayoutHelper.createFrame(44, 44, Gravity.TOP | Gravity.LEFT, 58, 0, 0, 0);
            lp.topMargin = AndroidUtilities.statusBarHeight + AndroidUtilities.dp(15);
            frame.addView(button, lp);
            button.bringToFront();
        } catch (Throwable ignore) {
        }
    }
}
"""


def patch_settings_button():
    """Хук в createView() экрана настроек (SettingsActivity и/или ProfileActivity для своего профиля)."""
    name_ = "Кнопка FluxGram в шапке настроек"
    ui = f"{JAVA}/org/telegram/ui"
    hooked = []
    for name in ("SettingsActivity.java", "ProfileActivity.java"):
        path = f"{ui}/{name}"
        if not os.path.exists(path):
            continue
        txt = read(path)
        if "FluxSettingsInjector" in txt:
            hooked.append(name)
            continue
        m = re.search(r"public\s+View\s+createView\s*\(\s*Context\s+(\w+)\s*\)\s*\{", txt)
        if not m:
            continue
        ctx = m.group(1)
        new = (f"public View createView(Context {ctx}) {{\n"
               f"        View fluxRoot = createViewFluxOrig({ctx});\n"
               f"        FluxSettingsInjector.attach(this, fluxRoot);\n"
               f"        return fluxRoot;\n"
               f"    }}\n\n"
               f"    private View createViewFluxOrig(Context {ctx}) {{")
        write(path, txt[:m.start()] + new + txt[m.end():])
        hooked.append(name)
    # диагностика: какие файлы рисуют экран настроек
    for root, _, files in os.walk(ui):
        for fn in files:
            if fn.endswith(".java"):
                try:
                    if "PowerUsage" in read(os.path.join(root, fn)):
                        print(f"        [diag] 'PowerUsage' встречается в {os.path.relpath(os.path.join(root, fn), ui)}")
                except Exception:
                    pass
    if hooked:
        write(f"{ui}/FluxSettingsInjector.java", INJECTOR_JAVA)
        report(name_, True, False, f"(хук createView: {', '.join(hooked)})")
        return True
    report(name_, False, False, "(createView не найден ни в SettingsActivity, ни в ProfileActivity)")
    return False


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
    if not patch_settings_button():
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
