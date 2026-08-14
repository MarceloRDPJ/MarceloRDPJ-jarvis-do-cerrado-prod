package br.com.jarviscerrado.poco;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.TextView;

final class RodUi {
    static final int BG = Color.rgb(2, 6, 23);
    static final int SURFACE = Color.rgb(15, 29, 48);
    static final int LINE = Color.rgb(37, 58, 78);
    static final int MUTED = Color.rgb(166, 183, 200);
    static final int CYAN = Color.rgb(0, 180, 216);
    static final int GREEN = Color.rgb(16, 185, 129);
    static final int AMBER = Color.rgb(245, 158, 11);
    static final int RED = Color.rgb(239, 68, 68);

    private RodUi() { }
    static int dp(Context c, int value) { return Math.round(value * c.getResources().getDisplayMetrics().density); }
    static LinearLayout screen(Context c) {
        LinearLayout root = new LinearLayout(c);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(c, 22), dp(c, 24), dp(c, 22), dp(c, 30));
        root.setBackgroundColor(BG);
        return root;
    }
    static LinearLayout card(Context c) {
        LinearLayout card = new LinearLayout(c);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(c, 18), dp(c, 17), dp(c, 18), dp(c, 17));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(SURFACE); bg.setCornerRadius(dp(c, 18)); bg.setStroke(dp(c, 1), LINE);
        card.setBackground(bg);
        card.setElevation(dp(c, 2));
        return card;
    }
    static LinearLayout.LayoutParams cardParams(Context c) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.setMargins(0, dp(c, 7), 0, dp(c, 7)); return p;
    }
    static TextView text(Context c, String value, int size, int color, boolean bold) {
        TextView view = new TextView(c); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        return view;
    }
    static TextView label(Context c, String value) {
        TextView view = text(c, value, 11, CYAN, true); view.setLetterSpacing(.12f); return view;
    }
    static TextView section(Context c, String value) {
        TextView view = label(c, value); view.setPadding(0, dp(c, 25), 0, dp(c, 7)); return view;
    }
    static TextView metric(Context c, String value) {
        TextView view = text(c, value, 23, Color.WHITE, true); view.setPadding(0, dp(c, 9), 0, dp(c, 7)); return view;
    }
    static LinearLayout statusRow(Context c, String name, String status, int color) {
        LinearLayout row = new LinearLayout(c); row.setGravity(Gravity.CENTER_VERTICAL); row.setPadding(0, dp(c, 8), 0, dp(c, 8));
        TextView dot = text(c, "●", 15, color, true); row.addView(dot);
        TextView title = text(c, name, 15, Color.WHITE, true); title.setPadding(dp(c, 10), 0, 0, 0); row.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        row.addView(text(c, status, 12, MUTED, false)); return row;
    }
}
