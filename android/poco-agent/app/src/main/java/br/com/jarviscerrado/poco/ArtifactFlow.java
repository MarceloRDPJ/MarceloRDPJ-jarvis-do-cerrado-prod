package br.com.jarviscerrado.poco;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.PowerManager;
import java.util.UUID;
import org.json.JSONObject;

/**
 * Entrega os dois artefatos de uma fatura: o Pix copia e cola e o PDF oficial.
 *
 * Pagamento esta fora de escopo por decisao de projeto, nao por falta de tempo.
 * Nenhum caminho deste arquivo abre banco, confirma Pix ou gera transacao: ele
 * entrega ao proprietario o que ele mesmo usaria para pagar, e para ai.
 *
 * O fluxo comeca refazendo a consulta por {@link EquatorialReader}. Parece
 * desperdicio e nao e: o pedido do artefato chega minutos depois da consulta,
 * quando a aba pode ter mudado, a sessao pode ter caido e a fatura pode ja ter
 * sido paga. Refazer a consulta e o que garante que o artefato pertence a fatura
 * que esta em aberto AGORA, e reusa inteira a maquina de sessao do motor
 * principal em vez de manter uma copia divergente dela aqui.
 *
 * A referencia pedida e conferida contra a referencia lida. Divergencia e recusa:
 * entregar o Pix de outro mes e pior do que nao entregar nada.
 */
final class ArtifactFlow {
    /** Rede de segurança do passo de artefato; cada passo interno tem prazo próprio. */
    static final long CALL_TIMEOUT_MILLIS = 90_000L;
    /** Margem para o broadcast, a tela acordar e a montagem da resposta. */
    private static final long BUDGET_MARGIN_MILLIS = 30_000L;
    /** O motor WebView so e acionado se sobrar tempo para ele terminar. */
    static final long WEBVIEW_MIN_MILLIS = 90_000L;

    private ArtifactFlow() { }

    /** Pix copia e cola da fatura em aberto, lido do QR da propria linha dela. */
    static JSONObject pix(Context context, String property, String reference) throws Exception {
        JSONObject bill = EquatorialReader.read(context, property);
        String target = agreedReference(bill, reference);

        PowerManager.WakeLock wake = screenWake(context, "rod:equatorial-pix");
        try {
            JSONObject step = call(context, "pix_equatorial", target);
            // A validacao acontece aqui tambem, e nao so na ponte: quem devolve o
            // payload ao Pi e este metodo, e a garantia tem de estar onde a
            // entrega esta.
            String payload = PixPayload.validate(step.optString("pix", ""));
            RodLog.found("pix", "payload valido", true);
            return metadata(context, bill, property, target)
                .put("source", "equatorial_pix_qr")
                .put("pix", payload)
                .put("pix_available", true);
        } finally {
            if (wake.isHeld()) wake.release();
        }
    }

    /** PDF oficial da fatura, baixado com a sessao do ROD e entregue por artifact_id. */
    static JSONObject boleto(Context context, String property, String reference) throws Exception {
        JSONObject bill = EquatorialReader.read(context, property);
        String target = agreedReference(bill, reference);

        PowerManager.WakeLock wake = screenWake(context, "rod:equatorial-boleto");
        try {
            JSONObject step = call(context, "boleto_equatorial", target);
            int index = step.optInt("invoice_index", -1);
            if (index < 0)
                throw new IllegalStateException(
                    "EQUATORIAL_BOLETO_NOT_FOUND: a fatura pedida nao esta na lista de downloads");

            String url = BoletoUrl.forInvoice(index);
            String cookie = cookieFor(context, property, url);
            byte[] pdf = BoletoDownloader.fetch(url, cookie);
            String artifactId = ArtifactUploader.upload(context, pdf, BoletoContent.PDF_MIME, "boleto");

            return metadata(context, bill, property, target)
                .put("source", "equatorial_boleto_pdf")
                .put("artifact_id", artifactId)
                .put("mime", BoletoContent.PDF_MIME)
                .put("size_bytes", pdf.length)
                .put("boleto_available", true);
        } finally {
            if (wake.isHeld()) wake.release();
        }
    }

    /**
     * Cookies da sessao para esta URL, do WebView do proprio ROD.
     *
     * Nao existe API para ler cookie do Chrome, e nao se tenta: alcancar arquivo
     * privado de outro app ou pedir permissao ampla de armazenamento seria trocar
     * um problema tecnico por um problema de privacidade. Se o jar do ROD estiver
     * vazio, quem autentica e o motor WebView do ROD — de novo, so consulta.
     */
    private static String cookieFor(Context context, String property, String url) throws Exception {
        String cookie = BoletoDownloader.sessionCookie(url);
        if (!cookie.isEmpty()) return cookie;

        RodLog.step("boleto", "jar do ROD sem sessao; autenticando o motor proprio");
        BillingConfig config = BillingConfig.load(context);
        String normalized = EquatorialReader.normalizeProperty(property);
        String unit = digits(config.value(normalized + "_energy"));
        String document = digits(config.value("equatorial_cpf"));
        if (unit.isEmpty() || document.isEmpty())
            throw new IllegalStateException(
                "EQUATORIAL_AUTH_REQUIRED: o cofre nao tem unidade e documento para autenticar o download");

        EquatorialWebEngine.read(context, unit, document,
            System.currentTimeMillis() + WEBVIEW_MIN_MILLIS);
        cookie = BoletoDownloader.sessionCookie(url);
        if (cookie.isEmpty())
            throw new IllegalStateException(
                "EQUATORIAL_AUTH_REQUIRED: o motor WebView do ROD nao obteve sessao para o download");
        return cookie;
    }

    /**
     * Referencia acordada entre o que foi pedido e o que o portal mostra agora.
     *
     * Sem pedido explicito, vale a fatura em aberto que a consulta acabou de ler.
     * Com pedido, as duas tem de coincidir.
     */
    private static String agreedReference(JSONObject bill, String requested) {
        String observed = PixRowLocator.normalizeReference(bill.optString("reference", ""));
        String wanted = PixRowLocator.normalizeReference(requested);
        if (wanted.isEmpty()) {
            if (observed.isEmpty())
                throw new IllegalStateException(
                    "EQUATORIAL_BILL_NOT_FOUND: a consulta nao devolveu a referencia da fatura");
            return observed;
        }
        if (!observed.isEmpty() && !observed.equals(wanted))
            throw new IllegalStateException(
                "EQUATORIAL_BILL_NOT_FOUND: a fatura em aberto agora e de outra referencia");
        return wanted;
    }

    /**
     * Metadado nao sensivel do artefato.
     *
     * Valor, vencimento e referencia acompanham porque e isso que permite ao
     * proprietario reconhecer a fatura. Codigo de barras e Pix vindos do parser
     * NAO entram: o unico Pix que sai daqui e o que passou pela validacao.
     */
    private static JSONObject metadata(Context context, JSONObject bill, String property, String reference)
            throws Exception {
        return new JSONObject()
            .put("provider", "equatorial")
            .put("property", EquatorialReader.normalizeProperty(property))
            .put("reference", reference)
            .put("amount", bill.optString("amount", ""))
            .put("due_date", bill.optString("due_date", ""))
            .put("retrieved_at", System.currentTimeMillis() / 1000L)
            .put("read_only", true);
    }

    /** A tela precisa ficar acesa: o passo de artefato depende do que esta renderizado. */
    private static PowerManager.WakeLock screenWake(Context context, String tag) {
        PowerManager.WakeLock wake = context.getSystemService(PowerManager.class).newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP, tag);
        wake.acquire(CALL_TIMEOUT_MILLIS + BUDGET_MARGIN_MILLIS);
        return wake;
    }

    /**
     * Um passo da ponte de acessibilidade.
     *
     * Copia deliberada do despacho do {@link EquatorialReader}: aquele metodo e
     * privado e o arquivo pertence a outro dono. Duplicar dez linhas custa menos
     * do que abrir a fila de jobs para um chamador generico.
     */
    private static JSONObject call(Context context, String operation, String reference) throws Exception {
        RodLog.step("artefato", "passo: " + operation);
        String request = UUID.randomUUID().toString();
        Intent intent = new Intent(JarvisAccessibilityService.ACTION_BRIDGE)
            .setPackage(context.getPackageName())
            .putExtra("request_id", request)
            .putExtra("operation", operation);
        if (reference != null) intent.putExtra("reference", reference);
        context.sendBroadcast(intent);

        SharedPreferences prefs = context.getSharedPreferences(
            JarvisAccessibilityService.PREFS_BRIDGE, Context.MODE_PRIVATE);
        long deadline = System.currentTimeMillis() + CALL_TIMEOUT_MILLIS;
        while (System.currentTimeMillis() < deadline) {
            if (request.equals(prefs.getString("request_id", ""))) {
                if (!prefs.getBoolean("ok", false))
                    throw new IllegalStateException(prefs.getString("error", "Falha no artefato da Equatorial"));
                return new JSONObject(prefs.getString("payload", "{}"));
            }
            Thread.sleep(100);
        }
        throw new IllegalStateException(
            "EQUATORIAL_PORTAL_TIMEOUT: a automacao nao respondeu no passo " + operation);
    }

    private static String digits(String value) {
        return value == null ? "" : value.replaceAll("\\D", "");
    }
}
