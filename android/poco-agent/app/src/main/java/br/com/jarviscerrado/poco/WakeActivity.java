package br.com.jarviscerrado.poco;

import android.app.Activity;
import android.app.KeyguardManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;

/** Wakes and dismisses only an unsecured/swipe keyguard before a local RPA read. */
public final class WakeActivity extends Activity {
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        setShowWhenLocked(true);
        setTurnScreenOn(true);
        KeyguardManager keyguard = getSystemService(KeyguardManager.class);
        if (keyguard == null || !keyguard.isKeyguardLocked()) {
            finish();
            return;
        }
        keyguard.requestDismissKeyguard(this, new KeyguardManager.KeyguardDismissCallback() {
            @Override public void onDismissSucceeded() { finish(); }
            @Override public void onDismissCancelled() { finish(); }
            @Override public void onDismissError() { finish(); }
        });
        new Handler(Looper.getMainLooper()).postDelayed(this::finish, 1200);
    }
}
