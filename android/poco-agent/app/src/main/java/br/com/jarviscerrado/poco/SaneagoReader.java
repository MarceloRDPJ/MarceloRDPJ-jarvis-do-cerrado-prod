package br.com.jarviscerrado.poco;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.PowerManager;
import java.util.UUID;
import org.json.JSONObject;

public final class SaneagoReader {
    private SaneagoReader() { }

    public static JSONObject readCurrent(Context context) throws Exception {
        PowerManager power = context.getSystemService(PowerManager.class);
        PowerManager.WakeLock wakeLock = power.newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP,
            "jarvis:poco-bill-read"
        );
        wakeLock.acquire(60_000);
        try {
            call(context, "open_saneago");
            Exception last = null;
            for (int attempt = 0; attempt < 5; attempt++) {
                Thread.sleep(3000);
                try { return call(context, "read_saneago"); }
                catch (Exception error) { last = error; }
            }
            throw last == null ? new IllegalStateException("Saneago sem resposta") : last;
        } finally {
            if (wakeLock.isHeld()) wakeLock.release();
        }
    }

    private static JSONObject call(Context context, String operation) throws Exception {
        String request = UUID.randomUUID().toString();
        Intent intent = new Intent(JarvisAccessibilityService.ACTION_BRIDGE)
            .setPackage(context.getPackageName())
            .putExtra("request_id", request).putExtra("operation", operation);
        context.sendBroadcast(intent);
        SharedPreferences prefs = context.getSharedPreferences(JarvisAccessibilityService.PREFS_BRIDGE, Context.MODE_PRIVATE);
        long deadline = System.currentTimeMillis() + 15_000;
        while (System.currentTimeMillis() < deadline) {
            if (request.equals(prefs.getString("request_id", ""))) {
                if (!prefs.getBoolean("ok", false)) throw new IllegalStateException(prefs.getString("error", "Falha na acessibilidade"));
                return new JSONObject(prefs.getString("payload", "{}"));
            }
            Thread.sleep(100);
        }
        throw new IllegalStateException("Servico de acessibilidade nao respondeu");
    }
}
