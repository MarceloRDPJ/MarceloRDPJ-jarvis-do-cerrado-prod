package br.com.jarviscerrado.poco;

import android.content.Context;
import android.content.Intent;
import java.util.List;
import org.json.JSONObject;

/** Read-only extractor. It deliberately excludes holder name and address. */
public final class SaneagoReader {
    private static final String PACKAGE = "br.com.saneago";
    private SaneagoReader() { }

    public static JSONObject readCurrent(Context context) throws Exception {
        Intent launch = context.getPackageManager().getLaunchIntentForPackage(PACKAGE);
        if (launch == null) throw new IllegalStateException("Aplicativo Saneago nao instalado");
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(launch);
        Thread.sleep(4000);
        List<String> text = JarvisAccessibilityService.visibleText(PACKAGE);
        if (text.isEmpty()) throw new IllegalStateException("Saneago nao visivel ou acessibilidade indisponivel");
        return new JSONObject()
            .put("source", "saneago_android_app")
            .put("account", valueAfterPrefix(text, "Conta:"))
            .put("amount", valueAfter(text, "Fatura atual"))
            .put("reference", valueAfter(text, "Referencia", "Referência"))
            .put("due_date", valueAfter(text, "Vencimento"))
            .put("consumption", valueAfter(text, "Consumo"))
            .put("read_only", true);
    }

    private static String valueAfterPrefix(List<String> values, String prefix) {
        for (String value : values) if (value.startsWith(prefix)) return value.substring(prefix.length()).trim();
        return "";
    }

    private static String valueAfter(List<String> values, String... labels) {
        for (int i = 0; i < values.size() - 1; i++)
            for (String label : labels) if (values.get(i).equalsIgnoreCase(label)) return values.get(i + 1);
        return "";
    }
}
