package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import org.junit.Test;

/**
 * Regras do download do boleto oficial.
 *
 * O "PDF" destes testes e um cabecalho valido seguido da palavra
 * EXEMPLOFICTICIO. Nenhuma fatura real, nenhum numero real.
 *
 * O que estes testes protegem: uma sessao caida nao responde 401. O portal
 * responde 200 com a tela de login em HTML, e sem estas checagens o proprietario
 * receberia uma pagina de login com nome de boleto — e, pior, acreditaria que
 * tinha o boleto.
 */
public class BoletoDownloadTest {

    private static final byte[] FAKE_PDF =
        "%PDF-1.4\nEXEMPLOFICTICIO\n%%EOF\n".getBytes(StandardCharsets.UTF_8);
    private static final byte[] LOGIN_PAGE =
        "<!DOCTYPE html><html><body><form>Login</form></body></html>".getBytes(StandardCharsets.UTF_8);

    // --------------------------------------------------------------- conteudo

    @Test
    public void acceptsOnlyWhatIsReallyAPdf() {
        assertArrayEquals(FAKE_PDF, BoletoContent.requirePdf(FAKE_PDF, "application/pdf"));
        assertArrayEquals(FAKE_PDF, BoletoContent.requirePdf(FAKE_PDF, "application/pdf; charset=binary"));
    }

    @Test
    public void htmlDisguisedAsPdfIsSessionExpiredAndNotACorruptFile() {
        // A diferenca importa: "refaca o login" e acionavel, "arquivo corrompido"
        // manda o proprietario tentar de novo para sempre.
        try {
            BoletoContent.requirePdf(LOGIN_PAGE, "application/pdf");
            fail("tela de login nao pode passar por boleto");
        } catch (IllegalStateException error) {
            assertTrue(error.getMessage().contains("EQUATORIAL_AUTH_REQUIRED"));
        }
    }

    @Test
    public void aPdfDeclaredAsSomethingElseIsRefused() {
        try {
            BoletoContent.requirePdf(FAKE_PDF, "text/html; charset=utf-8");
            fail("tipo declarado incoerente tem de falhar");
        } catch (IllegalStateException error) {
            assertTrue(error.getMessage().contains("EQUATORIAL_BOLETO_NOT_FOUND"));
        }
    }

    @Test
    public void mimeCheckIgnoresParametersButNotTheType() {
        assertTrue(BoletoContent.isPdfMime("application/pdf"));
        assertTrue(BoletoContent.isPdfMime("APPLICATION/PDF; name=fatura"));
        assertFalse(BoletoContent.isPdfMime("application/pdfx"));
        assertFalse(BoletoContent.isPdfMime("text/html"));
        assertFalse(BoletoContent.isPdfMime(null));
    }

    @Test
    public void magicBytesAreCheckedAndNotGuessed() {
        assertTrue(BoletoContent.hasPdfMagic(FAKE_PDF));
        assertFalse(BoletoContent.hasPdfMagic(LOGIN_PAGE));
        assertFalse(BoletoContent.hasPdfMagic(new byte[]{0x25, 0x50}));
        assertFalse(BoletoContent.hasPdfMagic(null));
    }

    @Test
    public void emptyBodyIsRefused() {
        try {
            BoletoContent.requirePdf(new byte[0], "application/pdf");
            fail("arquivo vazio nao e boleto");
        } catch (IllegalStateException error) {
            assertTrue(error.getMessage().contains("EQUATORIAL_BOLETO_NOT_FOUND"));
        }
    }

    // ----------------------------------------------------------------- limite

    @Test
    public void readingStopsAtTheLimitInsteadOfMeasuringAfterwards() {
        byte[] big = new byte[64 * 1024];
        try {
            BoletoContent.readLimited(new ByteArrayInputStream(big), 8 * 1024);
            fail("o limite tem de interromper a leitura");
        } catch (Exception error) {
            assertTrue(error.getMessage().contains("EQUATORIAL_BOLETO_TOO_LARGE"));
        }
    }

    @Test
    public void readsTheWholeBodyWhenItFits() throws Exception {
        assertArrayEquals(FAKE_PDF,
            BoletoContent.readLimited(new ByteArrayInputStream(FAKE_PDF), BoletoContent.MAX_BYTES));
    }

    // -------------------------------------------------------------------- URL

    @Test
    public void urlIsBuiltHereAndNeverTakenFromThePage() {
        assertEquals(
            "https://goias.equatorialenergia.com.br"
                + "/AgenciaGO/Servi%C3%A7os/aberto/mostrarFaturaCodigoBarras.aspx?invoice=0",
            BoletoUrl.forInvoice(0));
        assertTrue(BoletoUrl.forInvoice(3).endsWith("?invoice=3"));
    }

    @Test
    public void onlyTheInvoiceNumberSurvivesTheOnclickFromThePortal() {
        String onclick = "javascript: window.location.href = "
            + "'/AgenciaGO/Serviços/aberto/mostrarFaturaCodigoBarras.aspx?invoice=2';";
        assertEquals(BoletoUrl.forInvoice(2), BoletoUrl.fromOnclick(onclick));
    }

    @Test
    public void aRewrittenLinkCannotRedirectTheAuthenticatedAgent() {
        // Se a pagina apontar para outro lugar, o download nao acontece: e para
        // la que os cookies de sessao iriam.
        String hostile = "javascript: window.location.href = 'https://exemplo.ficticio/coleta.aspx?invoice=0';";
        try {
            BoletoUrl.fromOnclick(hostile);
            fail("link fora do arquivo esperado tem de falhar");
        } catch (IllegalStateException error) {
            assertTrue(error.getMessage().contains("EQUATORIAL_BOLETO_NOT_FOUND"));
        }
        try {
            BoletoUrl.requireTrusted("https://exemplo.ficticio/boleto.pdf");
            fail("destino fora do portal tem de falhar");
        } catch (IllegalStateException error) {
            assertTrue(error.getMessage().contains("EQUATORIAL_BOLETO_NOT_FOUND"));
        }
    }

    @Test
    public void indexOutsideTheListIsRefused() {
        try {
            BoletoUrl.forInvoice(-1);
            fail("indice negativo nao existe");
        } catch (IllegalStateException expected) {
            assertTrue(expected.getMessage().contains("EQUATORIAL_BOLETO_NOT_FOUND"));
        }
        try {
            BoletoUrl.forInvoice(BoletoUrl.MAX_INVOICE_INDEX + 1);
            fail("indice fora da lista nao existe");
        } catch (IllegalStateException expected) {
            assertTrue(expected.getMessage().contains("EQUATORIAL_BOLETO_NOT_FOUND"));
        }
    }
}
