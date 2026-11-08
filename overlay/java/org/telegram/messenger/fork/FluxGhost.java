package org.telegram.messenger.fork;

import android.os.SystemClock;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.FileLog;
import org.telegram.tgnet.ConnectionsManager;
import org.telegram.tgnet.TLObject;
import org.telegram.ui.ActionBar.AlertDialog;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.LaunchActivity;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.concurrent.ConcurrentHashMap;

/**
 * FluxGram ghost mode.
 *
 * Everything works on the network layer: ConnectionsManager.sendRequest(...) calls
 * {@link #intercept(int, TLObject)} before a request is serialized. TL classes are touched
 * only through reflection (by simple class name), so this file does not depend on where a
 * particular TL class lives in a given Telegram version.
 */
public class FluxGhost {

    private static final int K_NONE = 0;
    private static final int K_READ_MSG = 1;
    private static final int K_READ_STORY = 2;
    private static final int K_STATUS = 3;
    private static final int K_TYPING = 4;
    private static final int K_SEND = 5;
    private static final int K_REACTION = 6;

    private static final ConcurrentHashMap<Class<?>, Integer> KINDS = new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<String, Object> FIELDS = new ConcurrentHashMap<>();
    private static final ConcurrentHashMap<String, Long> READ_THROTTLE = new ConcurrentHashMap<>();

    private static final ThreadLocal<Boolean> BYPASS = new ThreadLocal<>();
    private static final ThreadLocal<Object> LAST_PASSED = new ThreadLocal<>();

    private static int kindOf(Class<?> c) {
        Integer cached = KINDS.get(c);
        if (cached != null) {
            return cached;
        }
        int kind;
        switch (c.getSimpleName()) {
            case "TL_messages_readHistory":
            case "TL_channels_readHistory":
            case "TL_messages_readDiscussion":
            case "TL_messages_readMessageContents":
            case "TL_channels_readMessageContents":
            case "TL_messages_readEncryptedHistory":
                kind = K_READ_MSG;
                break;
            case "TL_stories_readStories":
            case "TL_stories_incrementStoryViews":
                kind = K_READ_STORY;
                break;
            case "TL_account_updateStatus":
                kind = K_STATUS;
                break;
            case "TL_messages_setTyping":
            case "TL_messages_setEncryptedTyping":
                kind = K_TYPING;
                break;
            case "TL_messages_sendMessage":
            case "TL_messages_sendMedia":
            case "TL_messages_sendMultiMedia":
            case "TL_messages_sendInlineBotResult":
            case "TL_messages_forwardMessages":
                kind = K_SEND;
                break;
            case "TL_messages_sendReaction":
                kind = K_REACTION;
                break;
            default:
                kind = K_NONE;
        }
        KINDS.put(c, kind);
        return kind;
    }

    /**
     * Called from ConnectionsManager before a request is sent.
     *
     * @return true if the request must be dropped
     */
    public static boolean intercept(int account, TLObject req) {
        try {
            if (req == null || Boolean.TRUE.equals(BYPASS.get())) {
                return false;
            }
            if (LAST_PASSED.get() == req) { // same request passing through a nested sendRequest overload
                return false;
            }
            int kind = kindOf(req.getClass());
            if (kind == K_NONE) {
                return false;
            }
            boolean block = handle(account, req, kind);
            if (!block) {
                LAST_PASSED.set(req);
            }
            return block;
        } catch (Throwable t) {
            FileLog.e(t);
            return false;
        }
    }

    private static boolean handle(int account, TLObject req, int kind) {
        switch (kind) {
            case K_READ_MSG:
                return FluxConfig.get(FluxConfig.OPT_READ_MESSAGES);
            case K_READ_STORY:
                if (FluxConfig.get(FluxConfig.OPT_READ_STORIES)) {
                    return true;
                }
                return maybeAskAboutStories(account, req);
            case K_TYPING:
                return FluxConfig.get(FluxConfig.OPT_TYPING);
            case K_STATUS:
                return handleStatus(req);
            case K_SEND:
                applySilent(req);
                readOnAction(account, req);
                return false;
            case K_REACTION:
                readOnAction(account, req);
                return false;
        }
        return false;
    }

    // ------------------------------------------------------------------ online / offline

    private static boolean handleStatus(TLObject req) {
        Object offline = getField(req, "offline");
        if (!(offline instanceof Boolean) || (Boolean) offline) {
            return false; // "offline" updates always go through
        }
        if (FluxConfig.get(FluxConfig.OPT_AUTO_OFFLINE)) {
            setField(req, "offline", Boolean.TRUE); // never be "online": turn it into "offline"
            return false;
        }
        return FluxConfig.get(FluxConfig.OPT_ONLINE);
    }

    // ------------------------------------------------------------------ silent sending

    private static void applySilent(TLObject req) {
        int mode = FluxConfig.silentMode();
        if (mode == FluxConfig.SILENT_NEVER) {
            return;
        }
        if (mode != FluxConfig.SILENT_ALWAYS) {
            Object peer = getField(req, "peer");
            if (peer == null) {
                peer = getField(req, "to_peer");
            }
            if (peer == null) {
                return;
            }
            String pn = peer.getClass().getSimpleName();
            boolean group = pn.equals("TL_inputPeerChat") || pn.equals("TL_inputPeerChannel")
                    || pn.equals("TL_inputPeerChannelFromMessage");
            boolean priv = pn.equals("TL_inputPeerUser") || pn.equals("TL_inputPeerSelf")
                    || pn.equals("TL_inputPeerUserFromMessage");
            if (mode == FluxConfig.SILENT_GROUPS && !group) {
                return;
            }
            if (mode == FluxConfig.SILENT_PRIVATE && !priv) {
                return;
            }
        }
        setField(req, "silent", Boolean.TRUE);
    }

    // ------------------------------------------------------------------ "read on actions"

    private static void readOnAction(int account, TLObject req) {
        if (!FluxConfig.get(FluxConfig.OPT_READ_MESSAGES) || !FluxConfig.readOnActions()) {
            return;
        }
        Object peer = getField(req, "peer");
        if (peer == null) {
            peer = getField(req, "to_peer");
        }
        if (peer == null) {
            return;
        }
        try {
            String pn = peer.getClass().getSimpleName();
            Object id = getField(peer, "channel_id");
            if (id == null) id = getField(peer, "chat_id");
            if (id == null) id = getField(peer, "user_id");
            String key = account + ":" + pn + ":" + id;
            long now = SystemClock.elapsedRealtime();
            Long last = READ_THROTTLE.get(key);
            if (last != null && now - last < 1500) {
                return;
            }
            READ_THROTTLE.put(key, now);

            TLObject read;
            if (pn.equals("TL_inputPeerChannel")) {
                read = newTL("TL_channels_readHistory");
                TLObject channel = newTL("TL_inputChannel");
                if (read == null || channel == null) return;
                copyField(peer, channel, "channel_id");
                copyField(peer, channel, "access_hash");
                setField(read, "channel", channel);
                setField(read, "max_id", 0);
            } else if (pn.equals("TL_inputPeerChat") || pn.equals("TL_inputPeerUser") || pn.equals("TL_inputPeerSelf")) {
                read = newTL("TL_messages_readHistory");
                if (read == null) return;
                setField(read, "peer", peer);
                setField(read, "max_id", 0);
            } else {
                return;
            }
            sendBypass(account, read);
        } catch (Throwable t) {
            FileLog.e(t);
        }
    }

    // ------------------------------------------------------------------ "use scheduling"

    /**
     * Called from SendMessagesHelper.sendMessage(SendMessageParams): when "use scheduling" is on,
     * regular messages are sent as scheduled ones (~12 s ahead), so the account does not show up online.
     */
    public static void onSendParams(Object params, int account) {
        try {
            if (params == null || !FluxConfig.useSchedule()) {
                return;
            }
            Field fSchedule = params.getClass().getField("scheduleDate");
            if (fSchedule.getInt(params) != 0) {
                return;
            }
            Field fPeer = params.getClass().getField("peer");
            long peer = fPeer.getLong(params);
            if (peer == 0 || org.telegram.messenger.DialogObject.isEncryptedDialog(peer)) {
                return; // secret chats do not support scheduling
            }
            int now = ConnectionsManager.getInstance(account).getCurrentTime();
            fSchedule.setInt(params, now + 12);
        } catch (Throwable ignore) {
        }
    }

    // ------------------------------------------------------------------ stories: suggest ghost mode

    private static final ArrayList<Object[]> PENDING_STORY_REQUESTS = new ArrayList<>();
    private static boolean asking;
    private static long lastStoryRequest;

    private static boolean maybeAskAboutStories(int account, TLObject req) {
        if (!FluxConfig.suggestForStories()) {
            return false;
        }
        long now = SystemClock.elapsedRealtime();
        synchronized (PENDING_STORY_REQUESTS) {
            if (asking) {
                PENDING_STORY_REQUESTS.add(new Object[]{account, req});
                lastStoryRequest = now;
                return true;
            }
            boolean sameSession = now - lastStoryRequest < 30000;
            lastStoryRequest = now;
            if (sameSession || LaunchActivity.getLastFragment() == null) {
                return false;
            }
            asking = true;
            PENDING_STORY_REQUESTS.add(new Object[]{account, req});
        }
        AndroidUtilities.runOnUIThread(FluxGhost::showStoriesDialog);
        return true;
    }

    private static void showStoriesDialog() {
        try {
            BaseFragment fragment = LaunchActivity.getLastFragment();
            if (fragment == null || fragment.getParentActivity() == null) {
                finishStoriesDialog(true);
                return;
            }
            AlertDialog.Builder builder = new AlertDialog.Builder(fragment.getParentActivity());
            builder.setTitle(FluxConfig.t("Режим призрака", "Ghost mode"));
            builder.setMessage(FluxConfig.t(
                    "Автор увидит, что вы посмотрели историю. Включить «Не читать истории»?",
                    "The author will see that you viewed the story. Turn on \"Don't read stories\"?"));
            builder.setPositiveButton(FluxConfig.t("Включить", "Turn on"), (d, w) -> {
                FluxConfig.set(FluxConfig.OPT_READ_STORIES, true);
                finishStoriesDialog(false);
            });
            builder.setNegativeButton(FluxConfig.t("Продолжить", "Continue"), (d, w) -> finishStoriesDialog(true));
            AlertDialog dialog = builder.create();
            dialog.setCancelable(false);
            dialog.show();
        } catch (Throwable t) {
            FileLog.e(t);
            finishStoriesDialog(true);
        }
    }

    private static void finishStoriesDialog(boolean replay) {
        ArrayList<Object[]> copy;
        synchronized (PENDING_STORY_REQUESTS) {
            copy = new ArrayList<>(PENDING_STORY_REQUESTS);
            PENDING_STORY_REQUESTS.clear();
            asking = false;
        }
        if (replay) {
            for (Object[] item : copy) {
                sendBypass((Integer) item[0], (TLObject) item[1]);
            }
        }
    }

    // ------------------------------------------------------------------ helpers

    private static void sendBypass(int account, TLObject req) {
        try {
            BYPASS.set(Boolean.TRUE);
            ConnectionsManager.getInstance(account).sendRequest(req, (response, error) -> {
            });
        } catch (Throwable t) {
            FileLog.e(t);
        } finally {
            BYPASS.remove();
        }
    }

    private static TLObject newTL(String simpleName) {
        try {
            Class<?> c = Class.forName("org.telegram.tgnet.TLRPC$" + simpleName);
            return (TLObject) c.getDeclaredConstructor().newInstance();
        } catch (Throwable t) {
            return null;
        }
    }

    private static Field findField(Class<?> c, String name) {
        String key = c.getName() + "#" + name;
        Object cached = FIELDS.get(key);
        if (cached != null) {
            return cached instanceof Field ? (Field) cached : null;
        }
        try {
            Field f = c.getField(name);
            FIELDS.put(key, f);
            return f;
        } catch (Throwable t) {
            FIELDS.put(key, Boolean.FALSE);
            return null;
        }
    }

    private static Object getField(Object o, String name) {
        try {
            Field f = findField(o.getClass(), name);
            return f != null ? f.get(o) : null;
        } catch (Throwable t) {
            return null;
        }
    }

    private static void setField(Object o, String name, Object value) {
        try {
            Field f = findField(o.getClass(), name);
            if (f == null) {
                return;
            }
            if (value instanceof Integer && f.getType() == long.class) {
                f.setLong(o, ((Integer) value).longValue());
            } else {
                f.set(o, value);
            }
        } catch (Throwable ignore) {
        }
    }

    private static void copyField(Object from, Object to, String name) {
        setField(to, name, getField(from, name));
    }
}
