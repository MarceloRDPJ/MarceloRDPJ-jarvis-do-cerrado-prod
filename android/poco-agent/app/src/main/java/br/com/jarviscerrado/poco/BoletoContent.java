package br.com.jarviscerrado.poco;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;

/**
 * Julga o que voltou do portal ANTES de tratar como boleto.
 *
 * A armadilha documentada deste fluxo: uma sessao caida nao devolve 401. O
 * portal responde 200 com a tela de login em HTML, e sem verificacao o
 * proprietario receberia uma pagina de login com nome de boleto. Por isso sao
 * duas checagens independentes — o Content-Type declarado e os quatro primeiros
 * bytes do corpo — e a que vale mais e a dos bytes, porque cabecalho e afirmacao
 * e byte e fato.
 *
 * O limite de tamanho e aplicado durante a leitura, com contador. Ler tudo e
 * medir depois seria aceitar que a resposta escolhe quanta memoria o agente usa.
 *
 * Sem dependencia de Android: roda em teste de JVM.
 */
final class BoletoContent {
    static final String PDF_MIME = "application/pdf";
    /** Fatura da Equatorial e um PDF de poucas centenas de KB. */
    static final int MAX_BYTES = 2 * 1024 * 1024;
    private static final byte[] PDF_MAGIC = {0x25, 0x50, 0x44, 0x46};

    private BoletoContent() { }

    /** Verdadeiro so para application/pdf, com ou sem parametros. */
    static boolean isPdfMime(String contentType) {
        if (contentType == null) return false;
        return contentType.split(";")[0].trim().toLowerCase().equals(PDF_MIME);
    }

    /** Verdadeiro quando o corpo comeca com %PDF. */
    static boolean hasPdfMagic(byte[] body) {
        if (body == null || body.length < PDF_MAGIC.length) return false;
        for (int i = 0; i < PDF_MAGIC.length; i++) if (body[i] != PDF_MAGIC[i]) return false;
        return true;
    }

    /** Verdadeiro quando o corpo e, na verdade, uma pagina web. */
    static boolean looksLikeHtml(byte[] body) {
        if (body == null || body.length == 0) return false;
        String head = new String(body, 0, Math.min(body.length, 512)).trim().toLowerCase();
        return head.startsWith("<!doctype html") || head.startsWith("<html") || head.contains("<form");
    }

    /** Le no maximo {@code max} bytes e falha ao exceder, em vez de crescer sem limite. */
    static byte[] readLimited(InputStream stream, int max) throws Exception {
        if (stream == null)
            throw new IllegalStateException("EQUATORIAL_BOLETO_NOT_FOUND: o portal nao devolveu corpo");
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int total = 0;
        int count;
        while ((count = stream.read(buffer)) != -1) {
            total += count;
            if (total > max)
                throw new IllegalStateException(
                    "EQUATORIAL_BOLETO_TOO_LARGE: o download passou do limite de " + max + " bytes");
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    /**
     * Confirma que o corpo baixado e o PDF oficial.
     *
     * HTML no lugar do PDF significa sessao caida, nao arquivo corrompido, e o
     * codigo devolvido tem de dizer isso: e a diferenca entre "refaca o login" e
     * "tente de novo".
     */
    static byte[] requirePdf(byte[] body, String contentType) {
        if (body == null || body.length == 0)
            throw new IllegalStateException("EQUATORIAL_BOLETO_NOT_FOUND: o portal devolveu um arquivo vazio");
        if (looksLikeHtml(body) || !hasPdfMagic(body)) {
            if (looksLikeHtml(body))
                throw new IllegalStateException(
                    "EQUATORIAL_AUTH_REQUIRED: o portal devolveu a tela de login em vez do boleto");
            throw new IllegalStateException("EQUATORIAL_BOLETO_NOT_FOUND: o arquivo baixado nao e um PDF");
        }
        if (!isPdfMime(contentType))
            throw new IllegalStateException(
                "EQUATORIAL_BOLETO_NOT_FOUND: o portal declarou outro tipo de arquivo");
        return body;
    }
}
