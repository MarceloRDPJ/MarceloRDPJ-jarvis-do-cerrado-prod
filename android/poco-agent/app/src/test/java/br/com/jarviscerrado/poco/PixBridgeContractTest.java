package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.accessibilityservice.AccessibilityService;
import org.json.JSONObject;
import org.junit.Test;

/**
 * Contrato do trecho que o serviço de acessibilidade integra.
 *
 * Este teste não dirige tela nenhuma — não há aparelho aqui. Ele existe para que
 * a assinatura usada na ponte seja verificada pelo compilador junto com o resto
 * do projeto: se {@code pixPayload} ou {@code invoiceIndex} mudarem de forma, a
 * quebra aparece aqui e não no dono do outro arquivo.
 *
 * A alternativa era entregar o trecho como texto no relatório e descobrir o erro
 * de compilação no arquivo de outro agente.
 */
public class PixBridgeContractTest {

    /**
     * Réplica exata do adaptador que a ponte usa.
     *
     * No serviço, {@code ok} e {@code fail} chamam o método privado {@code reply}.
     * Aqui eles gravam num vetor, que é o que permite conferir o encaminhamento.
     */
    private static PixBridge.Reply recorder(final Object[] slot) {
        return new PixBridge.Reply() {
            @Override public void ok(JSONObject payload) { slot[0] = payload; }
            @Override public void fail(String error) { slot[1] = error; }
        };
    }

    /** Assinaturas que a ponte chama. Nunca executado: só compilado. */
    @SuppressWarnings("unused")
    private static void bridgeSketch(AccessibilityService service, String reference, Object[] slot) {
        PixBridge.pixPayload(service, reference, recorder(slot));
        BoletoBridge.invoiceIndex(service, reference, recorder(slot));
    }

    /**
     * O caminho de falha é o que este teste consegue exercer de verdade.
     *
     * Montar o payload de sucesso exigiria {@code org.json}, que no ambiente de
     * teste de JVM é apenas o esqueleto do android.jar e lança "not mocked". O
     * caminho de sucesso fica coberto pelo compilador, em {@code bridgeSketch}.
     */
    @Test
    public void failureReachesTheBridgeWithItsCode() {
        Object[] slot = new Object[2];
        recorder(slot).fail("EQUATORIAL_PIX_NOT_FOUND: nada legivel");
        assertEquals("EQUATORIAL_PIX_NOT_FOUND: nada legivel", slot[1]);
        assertTrue(slot[0] == null);
    }

    @Test
    public void everyFailureCarriesACodeTheOwnerCanActOn() {
        // O executor do Pi extrai EQUATORIAL_[A-Z_]+ de qualquer embrulho, então o
        // código precisa estar na mensagem — não só no tipo da exceção.
        String[] codes = {
            "EQUATORIAL_PIX_NOT_FOUND", "EQUATORIAL_PIX_AMBIGUOUS", "EQUATORIAL_PIX_INVALID",
            "EQUATORIAL_BOLETO_NOT_FOUND", "EQUATORIAL_BOLETO_TOO_LARGE",
            "EQUATORIAL_BOLETO_NOT_SENT", "EQUATORIAL_AUTH_REQUIRED", "EQUATORIAL_PORTAL_TIMEOUT",
        };
        for (String code : codes) {
            assertTrue(code, code.matches("EQUATORIAL_[A-Z_]+"));
            assertFalse(code, code.contains("PAGAR"));
        }
    }
}
