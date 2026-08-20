package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import java.util.Arrays;
import java.util.Collections;
import org.junit.Test;

/**
 * Regras do Pix copia e cola lido do QR da fatura.
 *
 * Todo payload aqui e SINTETICO: a chave e a palavra EXEMPLOFICTICIO seguida de
 * blocos de zeros, e o CRC e calculado dentro do proprio teste. Nenhum Pix real
 * aparece neste arquivo, e nenhum teste compara valor — comparam-se estrutura,
 * checksum e recusa.
 *
 * O que estes testes protegem: um payload aceito por engano e uma ordem de
 * pagamento. Aceitar "quase valido" seria pior do que nao entregar nada, e
 * corrigir um payload seria fabricar uma ordem que a Equatorial nao emitiu.
 */
public class PixPayloadTest {

    /** Monta um campo EMV: id de 2 digitos, tamanho de 2 digitos, valor. */
    private static String tlv(String id, String value) {
        return id + String.format("%02d", value.length()) + value;
    }

    /** BR Code sintetico completo, com CRC calculado aqui. */
    private static String syntheticPix() {
        String account = tlv("00", "BR.GOV.BCB.PIX")
            + tlv("01", "EXEMPLOFICTICIO-0000-0000-0000-0000");
        String body = "000201"
            + tlv("26", account)
            + tlv("52", "0000")
            + tlv("53", "986")
            + tlv("54", "1.00")
            + tlv("58", "BR")
            + tlv("59", "EXEMPLO FICTICIO")
            + tlv("60", "GOIANIA")
            + tlv("62", tlv("05", "***"))
            + "6304";
        return body + PixPayload.checksum(body);
    }

    // ------------------------------------------------------------------- CRC16

    @Test
    public void checksumFollowsTheOnlyVariantBacenAccepts() {
        // Vetor classico do CRC-16/CCITT-FALSE: polinomio 0x1021, inicial 0xFFFF,
        // sem reflexao. Se alguem trocar a variante, este teste cai.
        assertEquals("29B1", PixPayload.checksum("123456789"));
    }

    @Test
    public void checksumIsUppercaseHexWithFourDigits() {
        assertTrue(PixPayload.checksum("000201").matches("[0-9A-F]{4}"));
    }

    // -------------------------------------------------------------- aceitacao

    @Test
    public void acceptsASyntheticBrCodeAndReturnsItByteForByte() {
        String payload = syntheticPix();
        assertEquals(payload, PixPayload.validate(payload));
    }

    @Test
    public void tlvWalkCoversTheWholePayload() {
        assertTrue(PixPayload.wellFormed(syntheticPix()));
        // Um caractere sobrando no fim quebra a soma dos campos.
        assertFalse(PixPayload.wellFormed(syntheticPix() + "0"));
    }

    // ----------------------------------------------------------------- recusa

    @Test
    public void refusesAPayloadWhoseChecksumDoesNotClose() {
        String payload = syntheticPix();
        // Um digito trocado no valor: e exatamente o que o CRC existe para pegar.
        String tampered = payload.replace(tlv("54", "1.00"), tlv("54", "9.00"));
        assertFalse(tampered.equals(payload));
        expectCode(tampered, "EQUATORIAL_PIX_INVALID");
    }

    @Test
    public void neverRepairsAPayload() {
        String payload = syntheticPix();
        String tampered = payload.substring(0, payload.length() - 4) + "0000";
        try {
            PixPayload.validate(tampered);
            fail("um CRC que nao fecha tem de falhar, nunca ser corrigido");
        } catch (IllegalStateException expected) {
            // E o payload segue intocado: nada aqui reescreve o que veio do QR.
            assertTrue(tampered.endsWith("0000"));
        }
    }

    @Test
    public void refusesWhatIsNotABrCode() {
        expectCode("", "EQUATORIAL_PIX_NOT_FOUND");
        expectCode(null, "EQUATORIAL_PIX_NOT_FOUND");
        expectCode("https://exemplo.ficticio/pagar?fatura=0", "EQUATORIAL_PIX_INVALID");
        // Linha digitavel sintetica: numero longo, e nao BR Code.
        expectCode("8" + new String(new char[47]).replace('\0', '9'), "EQUATORIAL_PIX_INVALID");
    }

    @Test
    public void refusesABrCodeThatIsNotPix() {
        String account = tlv("00", "COM.OUTROARRANJO") + tlv("01", "EXEMPLOFICTICIO-0000");
        String body = "000201" + tlv("26", account) + tlv("58", "BR")
            + tlv("59", "EXEMPLO FICTICIO") + tlv("60", "GOIANIA") + "6304";
        expectCode(body + PixPayload.checksum(body), "EQUATORIAL_PIX_INVALID");
    }

    @Test
    public void refusesAPayloadWithoutTheCrcField() {
        String body = "000201" + tlv("26", tlv("00", "BR.GOV.BCB.PIX")
            + tlv("01", "EXEMPLOFICTICIO-0000-0000-0000-0000")) + tlv("59", "EXEMPLO FICTICIO");
        expectCode(body, "EQUATORIAL_PIX_INVALID");
    }

    @Test
    public void errorsNeverCarryThePayload() {
        String payload = syntheticPix().substring(0, syntheticPix().length() - 4) + "0000";
        try {
            PixPayload.validate(payload);
            fail("deveria falhar");
        } catch (IllegalStateException error) {
            assertFalse(error.getMessage().contains("EXEMPLOFICTICIO"));
            assertFalse(error.getMessage().contains("BR.GOV.BCB.PIX"));
        }
    }

    // ------------------------------------------------------------ unicidade

    @Test
    public void theSameQrSeenTwiceIsNotAmbiguous() {
        String payload = syntheticPix();
        assertEquals(payload, PixPayload.selectSingle(Arrays.asList(payload, payload)));
    }

    @Test
    public void twoDifferentQrCodesAreRefusedInsteadOfGuessed() {
        try {
            PixPayload.selectSingle(Arrays.asList(syntheticPix(), "000201OUTROQRSINTETICO"));
            fail("dois QR diferentes na tela nao permitem escolher");
        } catch (IllegalStateException error) {
            assertTrue(error.getMessage().contains("EQUATORIAL_PIX_AMBIGUOUS"));
            assertTrue(error.getMessage().contains("2"));
        }
    }

    @Test
    public void noQrAtAllIsAClearFailure() {
        try {
            PixPayload.selectSingle(Collections.<String>emptyList());
            fail("sem QR nao ha Pix");
        } catch (IllegalStateException error) {
            assertTrue(error.getMessage().contains("EQUATORIAL_PIX_NOT_FOUND"));
        }
    }

    private static void expectCode(String payload, String code) {
        try {
            PixPayload.validate(payload);
            fail("payload deveria ser recusado: esperado " + code);
        } catch (IllegalStateException error) {
            assertTrue(error.getMessage(), error.getMessage().contains(code));
        }
    }
}
