package br.com.jarviscerrado.poco;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.PowerManager;
import java.util.UUID;
import org.json.JSONObject;

public final class SaneagoReader {
    /**
     * The screen must stay awake for the whole flow. Session recovery (probe, login,
     * reopen, account selection, read retries) reaches roughly 190s, and a lock that
     * expired mid-flow used to blank the screen and break both the app and the OCR.
     */
    private static final long SCREEN_BUDGET_MILLIS = 240_000L;
    /** One bridge round trip. The OCR path with login recovery alone costs ~13s. */
    private static final long CALL_TIMEOUT_MILLIS = 25_000L;

    private SaneagoReader() { }

    public static JSONObject readCurrent(Context context, String property) throws Exception {
        BillingConfig billing = BillingConfig.load(context);
        if (!billing.saneagoReady())
            throw new IllegalStateException("Configure acesso e pelo menos uma conta Saneago no cofre do ROD");
        PowerManager power = context.getSystemService(PowerManager.class);
        PowerManager.WakeLock wakeLock = power.newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP,
            "jarvis:poco-bill-read"
        );
        wakeLock.acquire(SCREEN_BUDGET_MILLIS);
        try {
            call(context, "open_saneago");
            Thread.sleep(4000);
            try {
                call(context, "read_saneago");
            } catch (Exception error) {
                if (error.getMessage() != null && error.getMessage().contains("Sessao Saneago expirada")) {
                    call(context, "login_saneago", billing.value("saneago_login"), billing.value("saneago_password"));
                    Thread.sleep(6000);
                    call(context, "open_saneago");
                    Thread.sleep(4000);
                }
            }
            selectAccount(context, billing, property);
            Thread.sleep(3000);
            Exception last = null;
            for (int attempt = 0; attempt < 5; attempt++) {
                Thread.sleep(3000);
                try { return validateAccount(call(context, "read_saneago"), billing, property); }
                catch (Exception error) { last = error; }
            }
            if (last != null && last.getMessage() != null && last.getMessage().contains("Sessao Saneago expirada")) {
                call(context, "login_saneago", billing.value("saneago_login"), billing.value("saneago_password"));
                Thread.sleep(5000);
                call(context, "open_saneago");
                Thread.sleep(4000);
                selectAccount(context, billing, property);
                return validateAccount(call(context, "read_saneago"), billing, property);
            }
            throw last == null ? new IllegalStateException("Saneago sem resposta") : last;
        } finally {
            if (wakeLock.isHeld()) wakeLock.release();
        }
    }

    private static JSONObject call(Context context, String operation) throws Exception {
        return call(context, operation, null, null);
    }

    private static JSONObject validateAccount(JSONObject result, BillingConfig billing, String property) {
        String expected = normalizeAccount(billing.value(property + "_water"));
        if (expected.isEmpty()) throw new IllegalStateException("Conta Saneago nao configurada para " + property);
        String actual = normalizeAccount(result.optString("account", ""));
        if (actual.isEmpty())
            throw new IllegalStateException("Nao consegui ler o numero da conta; nao vou atribuir esta fatura a " + property);
        if (!actual.equals(expected))
            throw new IllegalStateException("O app Saneago esta em outra conta; selecione " + property + " no Poco e tente novamente");
        try { result.put("property", property); } catch (Exception ignored) { }
        return result;
    }

    private static JSONObject call(Context context, String operation, String login, String password) throws Exception {
        String request = UUID.randomUUID().toString();
        Intent intent = new Intent(JarvisAccessibilityService.ACTION_BRIDGE)
            .setPackage(context.getPackageName())
            .putExtra("request_id", request).putExtra("operation", operation);
        if (login != null) intent.putExtra("login", login);
        if (password != null) intent.putExtra("password", password);
        context.sendBroadcast(intent);
        SharedPreferences prefs = context.getSharedPreferences(JarvisAccessibilityService.PREFS_BRIDGE, Context.MODE_PRIVATE);
        long deadline = System.currentTimeMillis() + CALL_TIMEOUT_MILLIS;
        while (System.currentTimeMillis() < deadline) {
            if (request.equals(prefs.getString("request_id", ""))) {
                if (!prefs.getBoolean("ok", false)) throw new IllegalStateException(prefs.getString("error", "Falha na acessibilidade"));
                return new JSONObject(prefs.getString("payload", "{}"));
            }
            Thread.sleep(100);
        }
        throw new IllegalStateException("Servico de acessibilidade nao respondeu");
    }

    private static void selectAccount(Context context, BillingConfig billing, String property) throws Exception {
        String account = billing.value(property + "_water");
        if (account.replaceAll("\\D", "").isEmpty())
            throw new IllegalStateException("Conta Saneago nao configurada para " + property);
        String request = UUID.randomUUID().toString();
        Intent intent = new Intent(JarvisAccessibilityService.ACTION_BRIDGE)
            .setPackage(context.getPackageName()).putExtra("request_id", request)
            .putExtra("operation", "select_saneago").putExtra("account", account);
        context.sendBroadcast(intent);
        SharedPreferences prefs = context.getSharedPreferences(JarvisAccessibilityService.PREFS_BRIDGE, Context.MODE_PRIVATE);
        long deadline = System.currentTimeMillis() + CALL_TIMEOUT_MILLIS;
        while (System.currentTimeMillis() < deadline) {
            if (request.equals(prefs.getString("request_id", ""))) {
                if (!prefs.getBoolean("ok", false)) throw new IllegalStateException(prefs.getString("error", "Falha ao selecionar conta Saneago"));
                return;
            }
            Thread.sleep(100);
        }
        throw new IllegalStateException("Selecao da conta Saneago excedeu o tempo");
    }

    private static String normalizeAccount(String value) {
        String digits = value == null ? "" : value.replaceAll("\\D", "");
        return digits.replaceFirst("^0+(?!$)", "");
    }
}
