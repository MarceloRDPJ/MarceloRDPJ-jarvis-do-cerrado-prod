package br.com.jarviscerrado.poco;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Identifica a LINHA da fatura pedida na tabela de segunda via.
 *
 * A tabela tem uma linha por fatura em aberto e quatro colunas: mes/ano de
 * referencia, valor, download e pagamento via PIX. Acionar "o primeiro QR da
 * pagina" funcionaria enquanto houvesse uma unica fatura e entregaria o Pix da
 * fatura errada no primeiro mes com duas em aberto — que e exatamente quando o
 * proprietario mais precisa acertar.
 *
 * O portal escreve a referencia de dois jeitos, MM/AAAA e MMM/AAAA. Aqui os dois
 * normalizam para MM/AAAA, o mesmo formato que a consulta ja devolve.
 *
 * Sem dependencia de Android: roda em teste de JVM.
 */
final class PixRowLocator {
    /** Nenhuma linha corresponde a referencia pedida. */
    static final int NOT_FOUND = -1;
    /** Mais de uma linha corresponde: escolher seria adivinhar. */
    static final int AMBIGUOUS = -2;

    private static final String[] MONTHS =
        {"JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"};

    /**
     * MM/AAAA que nao seja o final de uma data completa.
     *
     * Sem o lookbehind, "vencimento 15/09/2026" entrava como se fosse a
     * referencia 09/2026: uma linha passaria a valer duas, o indice das faturas
     * seguintes sairia deslocado e o download traria a fatura errada.
     */
    private static final Pattern NUMERIC =
        Pattern.compile("(?<![\\d/.-])(0[1-9]|1[0-2])[/.-](20\\d{2})\\b");
    private static final Pattern NAMED = Pattern.compile(
        "(?i)\\b(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[A-Z]*[./-]\\s*(20\\d{2})\\b");

    private PixRowLocator() { }

    /** Converte "AGO/2026", "ago-2026" ou "08/2026" em "08/2026". Vazio se nao houver. */
    static String normalizeReference(String value) {
        if (value == null) return "";
        Matcher numeric = NUMERIC.matcher(value);
        if (numeric.find()) return numeric.group(1) + "/" + numeric.group(2);
        Matcher named = NAMED.matcher(value);
        if (named.find()) {
            String month = named.group(1).toUpperCase();
            for (int i = 0; i < MONTHS.length; i++)
                if (MONTHS[i].equals(month)) return String.format("%02d/%s", i + 1, named.group(2));
        }
        return "";
    }

    /** Verdadeiro quando o texto da linha carrega a referencia pedida. */
    static boolean matchesReference(String rowText, String reference) {
        String wanted = normalizeReference(reference);
        if (wanted.isEmpty() || rowText == null) return false;
        for (String found : references(rowText)) if (found.equals(wanted)) return true;
        return false;
    }

    /**
     * Ordinal da fatura pedida entre as faturas listadas.
     *
     * A ordem das linhas e a ordem do parametro invoice da propria pagina, e a
     * referencia aparece uma vez por linha. Contar as referencias na ordem em que
     * a arvore as devolve da o indice sem depender de reconhecer estrutura de
     * tabela na arvore de acessibilidade, que o Chrome nao expoe de forma estavel.
     *
     * Sem referencia pedida, so ha resposta quando existe exatamente uma fatura:
     * com duas, escolher seria adivinhar.
     */
    static int invoiceIndex(List<String> pageTexts, String reference) {
        // A referencia de uma linha aparece mais de uma vez: na celula e no titulo
        // do link. Contar as repeticoes deslocaria o indice das linhas seguintes,
        // e duas faturas nunca tem a mesma referencia — logo, deduplicar a pagina
        // inteira preserva a ordem real das linhas.
        List<String> found = new java.util.ArrayList<>();
        if (pageTexts != null)
            for (String text : pageTexts)
                for (String seen : references(text)) add(found, seen);

        String wanted = normalizeReference(reference);
        if (wanted.isEmpty()) return found.size() == 1 ? 0 : (found.isEmpty() ? NOT_FOUND : AMBIGUOUS);

        int index = NOT_FOUND;
        for (int i = 0; i < found.size(); i++) {
            if (!found.get(i).equals(wanted)) continue;
            if (index != NOT_FOUND) return AMBIGUOUS;
            index = i;
        }
        return index;
    }

    /**
     * Qual controle da linha e o do Pix, julgando apenas pelos rotulos.
     *
     * Um unico controle rotulado como Pix e a resposta. Dois seriam ambiguidade
     * de verdade — duas formas de pagar na mesma linha nao existem nesta pagina,
     * entao ler dois significa que a leitura esta errada. Nenhum devolve
     * NOT_FOUND, e ai quem decide e a geometria: a coluna de PIX e a ultima das
     * quatro.
     */
    static int preferPixLabel(List<String> labels) {
        if (labels == null) return NOT_FOUND;
        int found = NOT_FOUND;
        for (int i = 0; i < labels.size(); i++) {
            if (!isPixControl(labels.get(i))) continue;
            if (found != NOT_FOUND) return AMBIGUOUS;
            found = i;
        }
        return found;
    }

    /** Rotulo de um controle que abre o Pix da linha. */
    static boolean isPixControl(String label) {
        if (label == null) return false;
        String value = label.toLowerCase();
        return value.contains("pix") || value.contains("qr");
    }

    /** Referencias encontradas num texto, na ordem, sem repetir a mesma em sequencia. */
    private static List<String> references(String text) {
        List<String> result = new java.util.ArrayList<>();
        if (text == null) return result;
        Matcher numeric = NUMERIC.matcher(text);
        while (numeric.find()) add(result, numeric.group(1) + "/" + numeric.group(2));
        Matcher named = NAMED.matcher(text);
        while (named.find()) {
            String month = named.group(1).toUpperCase();
            for (int i = 0; i < MONTHS.length; i++)
                if (MONTHS[i].equals(month)) add(result, String.format("%02d/%s", i + 1, named.group(2)));
        }
        return result;
    }

    /**
     * A mesma referencia repetida na mesma celula e uma so fatura.
     *
     * O portal escreve "AGO/2026" e, no titulo do link, "08/2026". Contar as duas
     * deslocaria o indice de todas as linhas seguintes.
     */
    private static void add(List<String> result, String reference) {
        if (!result.contains(reference)) result.add(reference);
    }
}
