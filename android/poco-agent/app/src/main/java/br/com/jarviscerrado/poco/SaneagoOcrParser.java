package br.com.jarviscerrado.poco;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class SaneagoOcrParser {
    private SaneagoOcrParser() { }
    static Map<String, String> parse(String raw) {
        String text = raw == null ? "" : raw.replace('\u00a0', ' ');
        Map<String, String> values = new LinkedHashMap<>();
        values.put("account", capture(text, "(?i)Conta\\s*:?\\s*([0-9]{5,10}-?[0-9]?)"));
        values.put("amount", capture(text, "(?i)R\\$\\s*([0-9.]+,[0-9]{2})"));
        values.put("reference", capture(text, "(?i)Refer.ncia\\s*\\R+\\s*([0-9]{2}/[0-9]{4})"));
        values.put("due_date", capture(text, "(?i)Vencimento\\s*\\R+\\s*([0-9]{2}/[0-9]{2}/[0-9]{4})"));
        values.put("consumption", capture(text, "(?i)Consumo\\s*\\R+\\s*([0-9]+\\s*m[³3])"));
        StringBuilder missing = new StringBuilder();
        for (Map.Entry<String, String> entry : values.entrySet())
            if (entry.getValue().isEmpty()) {
                if (missing.length() > 0) missing.append(',');
                missing.append(entry.getKey());
            }
        if (missing.length() > 0) throw new IllegalStateException("OCR campos ausentes: " + missing);
        return values;
    }
    private static String capture(String text, String expression) {
        Matcher matcher = Pattern.compile(expression).matcher(text);
        return matcher.find() ? matcher.group(1).trim() : "";
    }
}
