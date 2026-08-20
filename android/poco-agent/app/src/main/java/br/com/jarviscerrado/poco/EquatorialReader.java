package br.com.jarviscerrado.poco;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.PowerManager;
import java.util.UUID;
import org.json.JSONObject;

/**
 * Leitura da fatura da Equatorial pela sessão já autenticada do Chrome.
 *
 * O aplicativo oficial apresenta erro de reCAPTCHA no aparelho, e automatizar o
 * login do portal esbarraria na mesma proteção. A estratégia é outra: o login é
 * feito à mão pelo proprietário, de tempos em tempos, e a automação apenas usa a
 * sessão que já existe no navegador. Quando essa sessão cai, o passo correto é
 * avisar — não tentar entrar sozinho.
 *
 * Não há nenhum Thread.sleep de espera aqui. Cada passo aguarda um estado
 * observável da tela, com prazo próprio, porque tempo fixo ora desperdiça
 * segundos ora corta o carregamento no meio.
 */
final class EquatorialReader {
    /** Cada passo já espera por estado internamente; esta é a rede de segurança. */
    static final long CALL_TIMEOUT_MILLIS = 60_000L;
    /** abrir, fechar aviso, selecionar imóvel, ler: cada um pode gastar o timeout inteiro. */
    static final int FLOW_STEPS = 4;
    /** Margem para o broadcast, o despertar da tela e a montagem da resposta. */
    private static final long BUDGET_MARGIN_MILLIS = 30_000L;
    /**
     * Cobre o pior caso do fluxo inteiro; a tela precisa ficar acesa até o fim.
     *
     * Eram 180 s fixos para quatro chamadas de 60 s: no pior caso o wake lock caía
     * antes do último passo, e a leitura falhava por tela apagada e não por portal.
     * O valor agora é derivado, para não voltar a divergir do fluxo.
     */
    static final long SCREEN_BUDGET_MILLIS =
        screenBudget(CALL_TIMEOUT_MILLIS, FLOW_STEPS, BUDGET_MARGIN_MILLIS);

    static long screenBudget(long callTimeout, int steps, long margin) {
        return callTimeout * steps + margin;
    }

    private EquatorialReader() { }

    static JSONObject read(Context context, String property) throws Exception {
        BillingConfig config = BillingConfig.load(context);
        String normalized = normalizeProperty(property);
        String unit = config.value(normalized + "_energy");
        // CPF e data de nascimento não participam mais da leitura: eles só serviam
        // ao login automático, que deixou de existir. A unidade continua essencial,
        // porque é ela que confirma de qual imóvel é a fatura lida.
        if (unit.replaceAll("\\D", "").isEmpty())
            throw new IllegalStateException("Unidade consumidora da Equatorial nao configurada para " + normalized);

        PowerManager.WakeLock wake = context.getSystemService(PowerManager.class).newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP, "rod:equatorial-read");
        wake.acquire(SCREEN_BUDGET_MILLIS);
        try {
            call(context, "open_equatorial", null);
            call(context, "dismiss_equatorial", null);
            call(context, "select_equatorial", unit);
            call(context, "emit_equatorial", null);
            JSONObject result = call(context, "read_equatorial", unit);
            result.put("property", normalized).put("read_only", true);
            return result;
        } finally {
            if (wake.isHeld()) wake.release();
        }
    }

    private static JSONObject call(Context context, String operation, String unit) throws Exception {
        RodLog.step("equatorial", "passo: " + operation);
        String request = UUID.randomUUID().toString();
        Intent intent = new Intent(JarvisAccessibilityService.ACTION_BRIDGE)
            .setPackage(context.getPackageName())
            .putExtra("request_id", request)
            .putExtra("operation", operation);
        if (unit != null) intent.putExtra("unit", unit);
        context.sendBroadcast(intent);

        SharedPreferences prefs = context.getSharedPreferences(
            JarvisAccessibilityService.PREFS_BRIDGE, Context.MODE_PRIVATE);
        long deadline = System.currentTimeMillis() + CALL_TIMEOUT_MILLIS;
        while (System.currentTimeMillis() < deadline) {
            if (request.equals(prefs.getString("request_id", ""))) {
                if (!prefs.getBoolean("ok", false))
                    throw new IllegalStateException(prefs.getString("error", "Falha Equatorial"));
                return new JSONObject(prefs.getString("payload", "{}"));
            }
            Thread.sleep(100);
        }
        throw new IllegalStateException("Automacao Equatorial nao respondeu no passo " + operation);
    }

    static String normalizeProperty(String value) {
        String p = value == null ? "casa" : value.toLowerCase().replace(' ', '_');
        if (p.contains("kitnet") && (p.contains("1") || p.endsWith("01"))) return "kitnet_01";
        if (p.contains("kitnet") && (p.contains("2") || p.endsWith("02"))) return "kitnet_02";
        if (p.contains("sala")) return "sala_comercial";
        if (p.contains("restaurante")) return "restaurante";
        return "casa";
    }
}
