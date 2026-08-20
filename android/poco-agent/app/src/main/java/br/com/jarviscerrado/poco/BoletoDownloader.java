package br.com.jarviscerrado.poco;

import android.webkit.CookieManager;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Baixa o PDF oficial da fatura usando a sessao legitima que o ROD ja tem.
 *
 * Objetivo: OBTER o arquivo. Nada aqui abre, interpreta ou extrai dado do PDF —
 * download nao e leitura, e o proprietario quer o boleto oficial, nao um resumo
 * feito por nos.
 *
 * Tres decisoes que valem explicacao:
 *
 * 1. O cookie e pedido para a URL COMPLETA do PDF, e nao para o host. O
 *    DownloadListener do WebView consulta apenas a base, e sessao ASP.NET
 *    costuma vir com cookie de path (/AgenciaGO): consultando a base, o
 *    download sai sem sessao e o portal responde a tela de login com HTTP 200.
 * 2. Redirecionamento nao e seguido. Neste fluxo um 302 e a tela de login, e
 *    seguir cegamente baixaria HTML com nome de PDF.
 * 3. O corpo e julgado pelos bytes, nao pelo cabecalho, e a checagem acontece
 *    antes de qualquer entrega.
 *
 * A origem do cookie e sempre o WebView do proprio ROD. Nao existe API para ler
 * cookie do Chrome, e tentar alcancar arquivo privado do Chrome ou pedir
 * permissao ampla de armazenamento seria trocar um problema tecnico por um
 * problema de privacidade.
 */
final class BoletoDownloader {
    /** A pagina que originou o link; ASP.NET as vezes exige Referer coerente. */
    static final String REFERER = BoletoUrl.HOST + "/AgenciaGO/Servi%C3%A7os/aberto/SegundaViaDownload.aspx";
    private static final int CONNECT_TIMEOUT_MILLIS = 10_000;
    private static final int READ_TIMEOUT_MILLIS = 30_000;

    private BoletoDownloader() { }

    /** Cookies da sessao do WebView do ROD para esta URL exata. */
    static String sessionCookie(String url) {
        try {
            String value = CookieManager.getInstance().getCookie(url);
            return value == null ? "" : value;
        } catch (Throwable unavailable) {
            return "";
        }
    }

    /**
     * Devolve os bytes do PDF, ou lanca erro tipado.
     *
     * O cookie entra por parametro para que o motor que detem a sessao possa
     * mudar sem mexer nesta funcao.
     */
    static byte[] fetch(String url, String cookieHeader) throws Exception {
        BoletoUrl.requireTrusted(url);
        if (cookieHeader == null || cookieHeader.isEmpty())
            throw new IllegalStateException(
                "EQUATORIAL_AUTH_REQUIRED: o motor autenticado do ROD nao tem sessao para baixar o boleto");

        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        try {
            connection.setRequestMethod("GET");
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(CONNECT_TIMEOUT_MILLIS);
            connection.setReadTimeout(READ_TIMEOUT_MILLIS);
            connection.setRequestProperty("Cookie", cookieHeader);
            connection.setRequestProperty("Accept", "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1");
            connection.setRequestProperty("Referer", REFERER);

            int code = connection.getResponseCode();
            RodLog.step("boleto", "portal respondeu HTTP " + code);
            if (code >= 300 && code < 400)
                throw new IllegalStateException(
                    "EQUATORIAL_AUTH_REQUIRED: o portal redirecionou o download para a tela de login");
            if (code == 401 || code == 403)
                throw new IllegalStateException(
                    "EQUATORIAL_AUTH_REQUIRED: o portal recusou o download desta sessao");
            if (code != 200)
                throw new IllegalStateException(
                    "EQUATORIAL_BOLETO_NOT_FOUND: o portal respondeu HTTP " + code + " no download");

            int declared = connection.getContentLength();
            if (declared > BoletoContent.MAX_BYTES)
                throw new IllegalStateException(
                    "EQUATORIAL_BOLETO_TOO_LARGE: o portal anunciou " + declared + " bytes");

            byte[] body = BoletoContent.readLimited(connection.getInputStream(), BoletoContent.MAX_BYTES);
            byte[] pdf = BoletoContent.requirePdf(body, connection.getContentType());
            RodLog.step("boleto", "pdf oficial recebido bytes=" + pdf.length);
            return pdf;
        } finally {
            connection.disconnect();
        }
    }
}
