package br.com.jarviscerrado.poco;

import android.util.Log;
import java.util.regex.Pattern;

/**
 * Trilha de execução do agente, legível por `adb logcat -s ROD`.
 *
 * O agente engolia toda exceção em silêncio. Cinco defeitos reais da automação
 * da Equatorial ficaram invisíveis por isso: cada tentativa só devolvia "falhou"
 * sem dizer em que passo. Sem esta trilha, depurar exige um ciclo completo de
 * build e instalação para cada hipótese.
 *
 * Nada sensível entra aqui. Sequências longas de dígitos — CPF, número da conta,
 * unidade consumidora — são mascaradas antes de sair, e valores de campo nunca
 * são registrados: registra-se o nome do campo e se ele ficou preenchido.
 */
final class RodLog {
    static final String TAG = "ROD";
    private static final Pattern LONG_DIGITS = Pattern.compile("\\d{5,}");

    private RodLog() { }

    static void step(String stage, String message) {
        Log.i(TAG, stage + " | " + sanitize(message));
    }

    static void fail(String stage, String message) {
        Log.w(TAG, stage + " | " + sanitize(message));
    }

    static String sanitize(String value) {
        if (value == null) return "";
        return LONG_DIGITS.matcher(value).replaceAll("<num>");
    }

    /** Descreve um valor sem revelá-lo: só presença e tamanho. */
    static String describe(String value) {
        if (value == null) return "nulo";
        if (value.isEmpty()) return "vazio";
        return "preenchido(" + value.length() + " chars)";
    }
}
