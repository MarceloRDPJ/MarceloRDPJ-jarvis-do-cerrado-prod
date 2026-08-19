package br.com.jarviscerrado.poco;

import android.util.Log;
import java.util.regex.Pattern;

/**
 * Trilha de execução do agente, legível por `adb logcat -s ROD`.
 *
 * O agente engolia toda exceção em silêncio, e cada tentativa só devolvia
 * "falhou" sem dizer em que passo. A trilha existe para tornar a automação
 * depurável sem um ciclo completo de build por hipótese.
 *
 * A primeira linha de defesa é não registrar conteúdo sensível: registra-se o
 * passo e se o campo foi encontrado, nunca o valor. A sanitização abaixo é a
 * segunda linha, para o caso de algo escapar por engano.
 */
final class RodLog {
    static final String TAG = "ROD";

    /** Sequências longas de dígitos: conta, unidade consumidora, código de barras. */
    private static final Pattern LONG_DIGITS = Pattern.compile("\\d{5,}");
    /** CPF e CNPJ formatados escapavam do padrão acima, que exige 5 dígitos seguidos. */
    private static final Pattern CPF = Pattern.compile("\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}");
    private static final Pattern CNPJ = Pattern.compile("\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}");
    /** Linha digitável de fatura, com ou sem separadores. */
    private static final Pattern DIGITABLE_LINE = Pattern.compile("[0-9][0-9.\\s]{25,}");
    /** Payload PIX copia e cola começa por 000201 e é longo. */
    private static final Pattern PIX_PAYLOAD = Pattern.compile("(?i)000201[0-9A-Z*./:+-]{20,}");
    /** Qualquer sequência de dígitos com separadores, como 0000 0000 0000. */
    private static final Pattern GROUPED_DIGITS = Pattern.compile("(?:\\d{3,}[\\s.-]){2,}\\d{2,}");

    private RodLog() { }

    static void step(String stage, String message) {
        Log.i(TAG, stage + " | " + sanitize(message));
    }

    static void fail(String stage, String message) {
        Log.w(TAG, stage + " | " + sanitize(message));
    }

    /** Registra apenas a presença de um campo, jamais o seu conteúdo. */
    static void found(String stage, String field, boolean present) {
        Log.i(TAG, stage + " | " + field + " encontrado=" + present);
    }

    static String sanitize(String value) {
        if (value == null) return "";
        String masked = PIX_PAYLOAD.matcher(value).replaceAll("<pix>");
        masked = CPF.matcher(masked).replaceAll("<doc>");
        masked = CNPJ.matcher(masked).replaceAll("<doc>");
        masked = DIGITABLE_LINE.matcher(masked).replaceAll("<linha>");
        masked = GROUPED_DIGITS.matcher(masked).replaceAll("<num>");
        return LONG_DIGITS.matcher(masked).replaceAll("<num>");
    }

    /** Descreve um valor sem revelá-lo: só presença e tamanho. */
    static String describe(String value) {
        if (value == null) return "nulo";
        if (value.isEmpty()) return "vazio";
        return "preenchido(" + value.length() + " chars)";
    }
}
