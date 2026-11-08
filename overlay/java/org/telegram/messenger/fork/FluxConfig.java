package org.telegram.messenger.fork;

import android.content.Context;
import android.content.SharedPreferences;

import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.LocaleController;

import java.util.Locale;

/**
 * FluxGram settings storage. Thread-safe, cheap to read from the network thread.
 */
public class FluxConfig {

    // Ghost mode options (order = order on the screen)
    public static final int OPT_READ_MESSAGES = 0;
    public static final int OPT_READ_STORIES = 1;
    public static final int OPT_ONLINE = 2;
    public static final int OPT_TYPING = 3;
    public static final int OPT_AUTO_OFFLINE = 4;
    public static final int OPT_COUNT = 5;

    // "Send without sound" modes
    public static final int SILENT_NEVER = 0;
    public static final int SILENT_ALWAYS = 1;
    public static final int SILENT_GROUPS = 2;
    public static final int SILENT_PRIVATE = 3;

    private static final String[] KEYS = {
            "ghost_no_read_messages",
            "ghost_no_read_stories",
            "ghost_no_online",
            "ghost_no_typing",
            "ghost_auto_offline"
    };

    private static volatile boolean loaded;
    private static volatile int valueMask;
    private static volatile int lockMask;
    private static volatile boolean readOnActions = true;
    private static volatile boolean useSchedule = false;
    private static volatile boolean suggestForStories = true;
    private static volatile int silentMode = SILENT_NEVER;

    private static SharedPreferences prefs() {
        return ApplicationLoader.applicationContext.getSharedPreferences("fluxgram_config", Context.MODE_PRIVATE);
    }

    private static synchronized void load() {
        if (loaded) {
            return;
        }
        try {
            SharedPreferences p = prefs();
            int v = 0, l = 0;
            for (int i = 0; i < OPT_COUNT; i++) {
                if (p.getBoolean(KEYS[i], false)) {
                    v |= (1 << i);
                }
                if (p.getBoolean(KEYS[i] + "_locked", false)) {
                    l |= (1 << i);
                }
            }
            valueMask = v;
            lockMask = l;
            readOnActions = p.getBoolean("ghost_read_on_actions", true);
            useSchedule = p.getBoolean("ghost_use_schedule", false);
            suggestForStories = p.getBoolean("ghost_suggest_stories", true);
            silentMode = p.getInt("send_silent_mode", SILENT_NEVER);
        } catch (Throwable ignore) {
        }
        loaded = true;
    }

    private static void saveBool(String key, boolean v) {
        try {
            prefs().edit().putBoolean(key, v).apply();
        } catch (Throwable ignore) {
        }
    }

    // ---------- ghost options ----------

    public static boolean get(int opt) {
        if (!loaded) load();
        return (valueMask & (1 << opt)) != 0;
    }

    public static void set(int opt, boolean value) {
        if (!loaded) load();
        valueMask = value ? (valueMask | (1 << opt)) : (valueMask & ~(1 << opt));
        saveBool(KEYS[opt], value);
    }

    public static boolean isLocked(int opt) {
        if (!loaded) load();
        return (lockMask & (1 << opt)) != 0;
    }

    public static void toggleLock(int opt) {
        if (!loaded) load();
        boolean now = !isLocked(opt);
        lockMask = now ? (lockMask | (1 << opt)) : (lockMask & ~(1 << opt));
        saveBool(KEYS[opt] + "_locked", now);
    }

    public static int enabledCount() {
        if (!loaded) load();
        return Integer.bitCount(valueMask);
    }

    /** Master switch: changes every option that is not locked. */
    public static void setAll(boolean value) {
        for (int i = 0; i < OPT_COUNT; i++) {
            if (!isLocked(i)) {
                set(i, value);
            }
        }
    }

    // ---------- other ghost settings ----------

    public static boolean readOnActions() {
        if (!loaded) load();
        return readOnActions;
    }

    public static void setReadOnActions(boolean v) {
        if (!loaded) load();
        readOnActions = v;
        saveBool("ghost_read_on_actions", v);
    }

    public static boolean useSchedule() {
        if (!loaded) load();
        return useSchedule;
    }

    public static void setUseSchedule(boolean v) {
        if (!loaded) load();
        useSchedule = v;
        saveBool("ghost_use_schedule", v);
    }

    public static boolean suggestForStories() {
        if (!loaded) load();
        return suggestForStories;
    }

    public static void setSuggestForStories(boolean v) {
        if (!loaded) load();
        suggestForStories = v;
        saveBool("ghost_suggest_stories", v);
    }

    public static int silentMode() {
        if (!loaded) load();
        return silentMode;
    }

    public static void setSilentMode(int mode) {
        if (!loaded) load();
        silentMode = mode;
        try {
            prefs().edit().putInt("send_silent_mode", mode).apply();
        } catch (Throwable ignore) {
        }
    }

    // ---------- tiny i18n helper (ru / en) ----------

    public static boolean isRu() {
        try {
            String lang = LocaleController.getInstance().getCurrentLocaleInfo().shortName;
            if (lang != null) {
                return lang.toLowerCase(Locale.ROOT).startsWith("ru");
            }
        } catch (Throwable ignore) {
        }
        return "ru".equals(Locale.getDefault().getLanguage());
    }

    public static String t(String ru, String en) {
        return isRu() ? ru : en;
    }
}
