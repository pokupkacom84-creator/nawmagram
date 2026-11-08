package org.telegram.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;

import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.R;
import org.telegram.messenger.fork.FluxConfig;
import org.telegram.ui.ActionBar.ActionBar;
import org.telegram.ui.ActionBar.AlertDialog;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.ActionBar.Theme;
import org.telegram.ui.Cells.HeaderCell;
import org.telegram.ui.Cells.TextCheckCell;
import org.telegram.ui.Cells.TextInfoPrivacyCell;
import org.telegram.ui.Cells.TextSettingsCell;
import org.telegram.ui.Components.LayoutHelper;
import org.telegram.ui.Components.RecyclerListView;
import org.telegram.ui.Components.Switch;

/**
 * Ghost mode screen (same layout as in AyuGram):
 *  - master switch "Ghost mode 5/5" with an expandable list of 5 options (long press = lock the value)
 *  - read on actions / use scheduling / send without sound / suggest ghost for stories
 */
public class FluxGhostModeActivity extends BaseFragment {

    private static final int T_HEADER = 0;
    private static final int T_MASTER = 1;
    private static final int T_CHECK = 2;
    private static final int T_INFO = 3;
    private static final int T_VALUE = 4;

    private RecyclerListView listView;
    private ListAdapter adapter;
    private boolean expanded = true;

    private int rowCount;
    private int headerRow;
    private int masterRow;
    private int optionsStartRow;
    private int optionsEndRow;
    private int lockInfoRow;
    private int readOnActionsRow;
    private int readOnActionsInfoRow;
    private int scheduleRow;
    private int scheduleInfoRow;
    private int silentRow;
    private int silentInfoRow;
    private int storiesRow;
    private int storiesInfoRow;

    @Override
    public boolean onFragmentCreate() {
        updateRows();
        return super.onFragmentCreate();
    }

    private void updateRows() {
        rowCount = 0;
        headerRow = rowCount++;
        masterRow = rowCount++;
        if (expanded) {
            optionsStartRow = rowCount;
            rowCount += FluxConfig.OPT_COUNT;
            optionsEndRow = rowCount;
        } else {
            optionsStartRow = -1;
            optionsEndRow = -1;
        }
        lockInfoRow = rowCount++;
        readOnActionsRow = rowCount++;
        readOnActionsInfoRow = rowCount++;
        scheduleRow = rowCount++;
        scheduleInfoRow = rowCount++;
        silentRow = rowCount++;
        silentInfoRow = rowCount++;
        storiesRow = rowCount++;
        storiesInfoRow = rowCount++;
    }

    private boolean isOptionRow(int position) {
        return optionsStartRow >= 0 && position >= optionsStartRow && position < optionsEndRow;
    }

    private static String optionTitle(int opt) {
        switch (opt) {
            case FluxConfig.OPT_READ_MESSAGES:
                return FluxConfig.t("Не читать сообщения", "Don't read messages");
            case FluxConfig.OPT_READ_STORIES:
                return FluxConfig.t("Не читать истории", "Don't read stories");
            case FluxConfig.OPT_ONLINE:
                return FluxConfig.t("Не отправлять «онлайн»", "Don't send \"online\"");
            case FluxConfig.OPT_TYPING:
                return FluxConfig.t("Не отправлять «печатает»", "Don't send \"typing\"");
            default:
                return FluxConfig.t("Автоматический «офлайн»", "Automatic \"offline\"");
        }
    }

    private static String silentModeTitle(int mode) {
        switch (mode) {
            case FluxConfig.SILENT_ALWAYS:
                return FluxConfig.t("Всегда", "Always");
            case FluxConfig.SILENT_GROUPS:
                return FluxConfig.t("В группах и каналах", "In groups and channels");
            case FluxConfig.SILENT_PRIVATE:
                return FluxConfig.t("В личных чатах", "In private chats");
            default:
                return FluxConfig.t("Никогда", "Never");
        }
    }

    @Override
    public View createView(Context context) {
        actionBar.setBackButtonImage(R.drawable.ic_ab_back);
        actionBar.setAllowOverlayTitle(true);
        actionBar.setTitle(FluxConfig.t("Режим Призрака", "Ghost Mode"));
        actionBar.setActionBarMenuOnItemClick(new ActionBar.ActionBarMenuOnItemClick() {
            @Override
            public void onItemClick(int id) {
                if (id == -1) {
                    finishFragment();
                }
            }
        });

        fragmentView = new FrameLayout(context);
        fragmentView.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundGray));
        FrameLayout frameLayout = (FrameLayout) fragmentView;

        listView = new RecyclerListView(context);
        listView.setLayoutManager(new LinearLayoutManager(context, LinearLayoutManager.VERTICAL, false));
        listView.setVerticalScrollBarEnabled(false);
        listView.setAdapter(adapter = new ListAdapter(context));
        frameLayout.addView(listView, LayoutHelper.createFrame(LayoutHelper.MATCH_PARENT, LayoutHelper.MATCH_PARENT));

        listView.setOnItemClickListener((view, position, x, y) -> {
            if (position == masterRow) {
                if (x >= view.getMeasuredWidth() - AndroidUtilities.dp(76)) {
                    // switch zone: toggle everything that is not locked
                    FluxConfig.setAll(FluxConfig.enabledCount() == 0);
                    adapter.notifyDataSetChanged();
                } else {
                    // text zone: expand / collapse
                    expanded = !expanded;
                    updateRows();
                    adapter.notifyDataSetChanged();
                }
            } else if (isOptionRow(position)) {
                int opt = position - optionsStartRow;
                boolean value = !FluxConfig.get(opt);
                FluxConfig.set(opt, value);
                if (view instanceof TextCheckCell) {
                    ((TextCheckCell) view).setChecked(value);
                }
                adapter.notifyItemChanged(masterRow);
            } else if (position == readOnActionsRow) {
                boolean value = !FluxConfig.readOnActions();
                FluxConfig.setReadOnActions(value);
                ((TextCheckCell) view).setChecked(value);
            } else if (position == scheduleRow) {
                boolean value = !FluxConfig.useSchedule();
                FluxConfig.setUseSchedule(value);
                ((TextCheckCell) view).setChecked(value);
            } else if (position == storiesRow) {
                boolean value = !FluxConfig.suggestForStories();
                FluxConfig.setSuggestForStories(value);
                ((TextCheckCell) view).setChecked(value);
            } else if (position == silentRow) {
                showSilentDialog();
            }
        });

        listView.setOnItemLongClickListener((view, position) -> {
            if (isOptionRow(position)) {
                FluxConfig.toggleLock(position - optionsStartRow);
                view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);
                adapter.notifyItemChanged(position);
                return true;
            }
            return false;
        });
        return fragmentView;
    }

    private void showSilentDialog() {
        if (getParentActivity() == null) {
            return;
        }
        final int[] modes = {
                FluxConfig.SILENT_NEVER, FluxConfig.SILENT_ALWAYS,
                FluxConfig.SILENT_GROUPS, FluxConfig.SILENT_PRIVATE
        };
        CharSequence[] titles = new CharSequence[modes.length];
        for (int i = 0; i < modes.length; i++) {
            titles[i] = silentModeTitle(modes[i]);
        }
        AlertDialog.Builder builder = new AlertDialog.Builder(getParentActivity());
        builder.setTitle(FluxConfig.t("Отправлять без звука", "Send without sound"));
        builder.setItems(titles, (dialog, which) -> {
            FluxConfig.setSilentMode(modes[which]);
            adapter.notifyItemChanged(silentRow);
        });
        showDialog(builder.create());
    }

    // ------------------------------------------------------------------ master cell

    private static class MasterCell extends FrameLayout {

        private final TextView title;
        private final Switch toggle;
        private final Paint dividerPaint = new Paint();

        MasterCell(Context context) {
            super(context);
            setWillNotDraw(false);
            setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundWhite));

            title = new TextView(context);
            title.setTextColor(Theme.getColor(Theme.key_windowBackgroundWhiteBlackText));
            title.setTextSize(16);
            title.setSingleLine(true);
            title.setGravity(Gravity.LEFT | Gravity.CENTER_VERTICAL);
            addView(title, LayoutHelper.createFrame(LayoutHelper.WRAP_CONTENT, LayoutHelper.MATCH_PARENT,
                    Gravity.LEFT | Gravity.TOP, 21, 0, 90, 0));

            toggle = new Switch(context);
            toggle.setColors(Theme.key_switchTrack, Theme.key_switchTrackChecked,
                    Theme.key_windowBackgroundWhite, Theme.key_windowBackgroundWhite);
            addView(toggle, LayoutHelper.createFrame(37, 20, Gravity.RIGHT | Gravity.CENTER_VERTICAL, 0, 0, 22, 0));
            dividerPaint.setColor(Theme.getColor(Theme.key_divider));
        }

        void set(boolean expanded, int count, int total) {
            title.setText(FluxConfig.t("Режим призрака", "Ghost mode") + "  " + count + "/" + total
                    + (expanded ? " \u25B4" : " \u25BE"));
            toggle.setChecked(count > 0, false);
        }

        @Override
        protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
            super.onMeasure(widthMeasureSpec,
                    MeasureSpec.makeMeasureSpec(AndroidUtilities.dp(50) + 1, MeasureSpec.EXACTLY));
        }

        @Override
        protected void onDraw(Canvas canvas) {
            float x = getMeasuredWidth() - AndroidUtilities.dp(76);
            canvas.drawLine(x, AndroidUtilities.dp(12), x, getMeasuredHeight() - AndroidUtilities.dp(12), dividerPaint);
        }
    }

    // ------------------------------------------------------------------ adapter

    private class ListAdapter extends RecyclerListView.SelectionAdapter {

        private final Context context;

        ListAdapter(Context context) {
            this.context = context;
        }

        @Override
        public int getItemCount() {
            return rowCount;
        }

        @Override
        public boolean isEnabled(RecyclerView.ViewHolder holder) {
            int type = holder.getItemViewType();
            return type == T_MASTER || type == T_CHECK || type == T_VALUE;
        }

        @Override
        public int getItemViewType(int position) {
            if (position == headerRow) {
                return T_HEADER;
            } else if (position == masterRow) {
                return T_MASTER;
            } else if (isOptionRow(position) || position == readOnActionsRow
                    || position == scheduleRow || position == storiesRow) {
                return T_CHECK;
            } else if (position == silentRow) {
                return T_VALUE;
            }
            return T_INFO;
        }

        @Override
        public RecyclerView.ViewHolder onCreateViewHolder(ViewGroup parent, int viewType) {
            View view;
            switch (viewType) {
                case T_HEADER:
                    view = new HeaderCell(context);
                    view.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundWhite));
                    break;
                case T_MASTER:
                    view = new MasterCell(context);
                    break;
                case T_CHECK:
                    view = new TextCheckCell(context);
                    view.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundWhite));
                    break;
                case T_VALUE:
                    view = new TextSettingsCell(context);
                    view.setBackgroundColor(Theme.getColor(Theme.key_windowBackgroundWhite));
                    break;
                default:
                    view = new TextInfoPrivacyCell(context);
                    break;
            }
            return new RecyclerListView.Holder(view);
        }

        @Override
        public void onBindViewHolder(RecyclerView.ViewHolder holder, int position) {
            switch (holder.getItemViewType()) {
                case T_HEADER:
                    ((HeaderCell) holder.itemView).setText(FluxConfig.t("Режим призрака", "Ghost mode"));
                    break;
                case T_MASTER:
                    ((MasterCell) holder.itemView).set(expanded, FluxConfig.enabledCount(), FluxConfig.OPT_COUNT);
                    break;
                case T_CHECK: {
                    TextCheckCell cell = (TextCheckCell) holder.itemView;
                    if (isOptionRow(position)) {
                        int opt = position - optionsStartRow;
                        String text = optionTitle(opt) + (FluxConfig.isLocked(opt) ? "  \uD83D\uDD12" : "");
                        cell.setTextAndCheck(text, FluxConfig.get(opt), position != optionsEndRow - 1);
                    } else if (position == readOnActionsRow) {
                        cell.setTextAndCheck(FluxConfig.t("Читать при действиях", "Read on actions"),
                                FluxConfig.readOnActions(), false);
                    } else if (position == scheduleRow) {
                        cell.setTextAndCheck(FluxConfig.t("Использовать отложку", "Use scheduling"),
                                FluxConfig.useSchedule(), false);
                    } else if (position == storiesRow) {
                        cell.setTextAndCheck(FluxConfig.t("Предлагать призрака для сторис", "Suggest ghost for stories"),
                                FluxConfig.suggestForStories(), false);
                    }
                    break;
                }
                case T_VALUE:
                    ((TextSettingsCell) holder.itemView).setTextAndValue(
                            FluxConfig.t("Отправлять без звука", "Send without sound"),
                            silentModeTitle(FluxConfig.silentMode()), false);
                    break;
                default: {
                    TextInfoPrivacyCell cell = (TextInfoPrivacyCell) holder.itemView;
                    if (position == lockInfoRow) {
                        cell.setText(FluxConfig.t(
                                "Зажмите любую опцию, чтобы зафиксировать её значение.",
                                "Long-press any option to lock its value."));
                    } else if (position == readOnActionsInfoRow) {
                        cell.setText(FluxConfig.t(
                                "Автоматически читает сообщение при отправке нового или при реакции на сообщение.",
                                "Automatically reads the chat when you send a new message or react to a message."));
                    } else if (position == scheduleInfoRow) {
                        cell.setText(FluxConfig.t(
                                "Автоматически ставит задержку в ~12 секунд (дольше для сообщений с вложениями) при отправке сообщений. При использовании этой функции вы не будете появляться в сети.\nНе рекомендуется использовать на слабом интернете.",
                                "Automatically delays sent messages by ~12 seconds (longer for messages with attachments). While it is on you will not appear online.\nNot recommended on a slow connection."));
                    } else if (position == silentInfoRow) {
                        cell.setText(FluxConfig.t(
                                "Отправляет сообщения по умолчанию без звука.",
                                "Sends messages silently by default."));
                    } else if (position == storiesInfoRow) {
                        cell.setText(FluxConfig.t(
                                "Показывает предупреждение перед открытием сторис, предлагая включить режим призрака.",
                                "Shows a warning before opening stories, suggesting to turn on ghost mode."));
                    }
                    break;
                }
            }
        }
    }
}
