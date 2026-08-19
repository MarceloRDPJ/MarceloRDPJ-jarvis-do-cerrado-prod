package br.com.jarviscerrado.poco;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.PowerManager;
import java.util.UUID;
import org.json.JSONObject;

final class EquatorialReader {
    /** Portal load, form fill and result render, with room for a slow mobile page. */
    private static final long SCREEN_BUDGET_MILLIS = 180_000L;
    private static final long CALL_TIMEOUT_MILLIS = 30_000L;

    private EquatorialReader() { }
    static JSONObject read(Context context, String property) throws Exception {
        BillingConfig config = BillingConfig.load(context);
        if (!config.equatorialReady()) throw new IllegalStateException("Configure CPF, nascimento e unidades Equatorial no cofre do ROD");
        String key = normalizeProperty(property) + "_energy";
        String unit = config.value(key);
        if (unit.isEmpty()) throw new IllegalStateException("Unidade Equatorial nao configurada para " + property);
        PowerManager.WakeLock wake = context.getSystemService(PowerManager.class).newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP, "rod:equatorial-read");
        wake.acquire(SCREEN_BUDGET_MILLIS);
        try {
            call(context, "open_equatorial", null, null, null);
            Thread.sleep(7000);
            // O aviso de privacidade cobre a pagina; sem fecha-lo o clique em
            // "Acessar" e aceito mas nao avanca.
            call(context, "dismiss_equatorial", null, null, null);
            Thread.sleep(2000);
            call(context, "fill_equatorial", config.value("equatorial_cpf"), config.value("equatorial_birth_date"), unit);
            Thread.sleep(12000);
            // A home leva para a Agencia Virtual, que pede unidade consumidora e CPF.
            call(context, "login_equatorial", config.value("equatorial_cpf"), null, unit);
            Thread.sleep(12000);
            JSONObject result = call(context, "read_equatorial", null, null, null);
            result.put("property", normalizeProperty(property)).put("read_only", true);
            return result;
        } finally { if (wake.isHeld()) wake.release(); }
    }
    private static JSONObject call(Context context, String operation, String cpf, String birth, String unit) throws Exception {
        RodLog.step("equatorial", "passo: " + operation);
        String request = UUID.randomUUID().toString();
        Intent intent = new Intent(JarvisAccessibilityService.ACTION_BRIDGE).setPackage(context.getPackageName())
            .putExtra("request_id", request).putExtra("operation", operation);
        if (cpf != null) intent.putExtra("cpf", cpf);
        if (birth != null) intent.putExtra("birth", birth);
        if (unit != null) intent.putExtra("unit", unit);
        context.sendBroadcast(intent);
        SharedPreferences prefs = context.getSharedPreferences(JarvisAccessibilityService.PREFS_BRIDGE, Context.MODE_PRIVATE);
        long deadline = System.currentTimeMillis() + CALL_TIMEOUT_MILLIS;
        while (System.currentTimeMillis() < deadline) {
            if (request.equals(prefs.getString("request_id", ""))) {
                if (!prefs.getBoolean("ok", false)) throw new IllegalStateException(prefs.getString("error", "Falha Equatorial"));
                return new JSONObject(prefs.getString("payload", "{}"));
            }
            Thread.sleep(100);
        }
        throw new IllegalStateException("Automacao Equatorial nao respondeu");
    }
    static String normalizeProperty(String value) {
        String p = value == null ? "casa" : value.toLowerCase().replace(' ', '_');
        if (p.contains("kitnet") && (p.contains("1") || p.endsWith("01"))) return "kitnet_01";
        if (p.contains("kitnet") && (p.contains("2") || p.endsWith("02"))) return "kitnet_02";
        if (p.contains("sala")) return "sala_comercial";
        return "casa";
    }
}
