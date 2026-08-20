package br.com.jarviscerrado.poco;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Monta a URL do PDF oficial da fatura.
 *
 * A pagina de resultado da segunda via aponta o download por
 * "window.location.href = '/AgenciaGO/Servi&ccedil;os/aberto/mostrarFaturaCodigoBarras.aspx?invoice=N'".
 * A URL nunca e usada como o portal a escreve: daqui sai sempre a partir de um
 * host e de um caminho fixos, e do portal aproveita-se apenas o numero da
 * fatura. Aceitar caminho vindo da pagina significaria deixar o portal (ou
 * qualquer coisa injetada nele) escolher para onde o agente autenticado envia os
 * cookies de sessao.
 *
 * Sem dependencia de Android: roda em teste de JVM.
 */
final class BoletoUrl {
    static final String HOST = "https://goias.equatorialenergia.com.br";
    /** Caminho ja percent-encoded; o "ç" do portal e %C3%A7. */
    static final String PATH = "/AgenciaGO/Servi%C3%A7os/aberto/mostrarFaturaCodigoBarras.aspx";
    /** A listagem de faturas em aberto e curta; alem disso e leitura errada. */
    static final int MAX_INVOICE_INDEX = 24;

    private static final Pattern INVOICE = Pattern.compile("(?i)invoice=(\\d{1,3})");
    private static final Pattern EXPECTED_FILE = Pattern.compile("(?i)mostrarFaturaCodigoBarras\\.aspx");

    private BoletoUrl() { }

    /** URL do PDF da n-esima fatura listada. */
    static String forInvoice(int index) {
        if (index < 0 || index > MAX_INVOICE_INDEX)
            throw new IllegalStateException("EQUATORIAL_BOLETO_NOT_FOUND: indice de fatura fora da lista");
        return HOST + PATH + "?invoice=" + index;
    }

    /**
     * Extrai o numero da fatura de um onclick do portal e reconstroi a URL aqui.
     *
     * O que vem da pagina e um numero e a confirmacao de que o arquivo e o
     * esperado. Todo o resto — esquema, host, caminho — e nosso.
     */
    static String fromOnclick(String onclick) {
        if (onclick == null || !EXPECTED_FILE.matcher(onclick).find())
            throw new IllegalStateException("EQUATORIAL_BOLETO_NOT_FOUND: link de download nao reconhecido");
        Matcher matcher = INVOICE.matcher(onclick);
        if (!matcher.find())
            throw new IllegalStateException("EQUATORIAL_BOLETO_NOT_FOUND: link de download sem numero de fatura");
        return forInvoice(Integer.parseInt(matcher.group(1)));
    }

    /** Recusa qualquer URL que nao seja https no dominio da Equatorial. */
    static void requireTrusted(String url) {
        if (url == null || !url.startsWith(HOST + PATH))
            throw new IllegalStateException("EQUATORIAL_BOLETO_NOT_FOUND: destino de download nao confiavel");
    }
}
