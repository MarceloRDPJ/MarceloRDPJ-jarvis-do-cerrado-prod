package br.com.jarviscerrado.poco;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class EquatorialTextParser {
    private EquatorialTextParser() { }
    static Map<String,String> parse(String raw) {
        String text = raw == null ? "" : raw.replace('\u00a0', ' ');
        String lower = text.toLowerCase();
        if (lower.contains("captcha") || lower.contains("verifique que voce") || lower.contains("access denied") || lower.contains("error 15"))
            throw new IllegalStateException("Equatorial exige verificacao humana no Poco");
        Map<String,String> out = new LinkedHashMap<>();
        out.put("amount", capture(text, "(?i)R\\$\\s*([0-9.]+,[0-9]{2})"));
        out.put("due_date", capture(text, "(?i)(?:vencimento|vence em)\\s*:?\\s*([0-9]{2}/[0-9]{2}/[0-9]{4})"));
        out.put("reference", capture(text, "(?i)(?:refer.ncia|m.s de refer.ncia)\\s*:?\\s*([0-9]{2}/[0-9]{4})"));
        if (out.get("amount").isEmpty() || out.get("due_date").isEmpty())
            throw new IllegalStateException("Fatura Equatorial nao encontrada na tela atual");
        return out;
    }
    private static String capture(String text, String regex) {
        Matcher m = Pattern.compile(regex).matcher(text); return m.find() ? m.group(1).trim() : "";
    }
}
