package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertThrows;
import static org.junit.Assert.assertTrue;
import java.util.Map;
import org.junit.Test;

public class OcrParserTest {
    @Test public void parsesSaneagoFinancialFields() throws Exception {
        String sample = "Conta: 123456-7\nFatura atual\nR$ 123,45\nReferência\n08/2026\n" +
            "Vencimento\n18/08/2026\nConsumo\n23m³\nPagamento\n2ª via";
        Map<String, String> result = SaneagoOcrParser.parse(sample);
        assertEquals("123456-7", result.get("account"));
        assertEquals("123,45", result.get("amount"));
        assertEquals("08/2026", result.get("reference"));
        assertEquals("18/08/2026", result.get("due_date"));
        assertEquals("23m³", result.get("consumption"));
    }

    @Test public void passiveRecaptchaBadgeIsNotAHumanCheck() {
        // O rodapé do portal carrega esse selo em toda página. Tratar isso como
        // bloqueio fazia a consulta falhar numa tela perfeitamente legível.
        String page = "Faturas e outros servicos\n"
            + "Vencimento: 18/08/2026\n"
            + "R$ 210,44\n"
            + "protegido por reCAPTCHA\n"
            + "Este site esta excedendo a cota gratuita do reCAPTCHA Enterprise";
        Map<String, String> result = EquatorialTextParser.parse(page);
        assertEquals("210,44", result.get("amount"));
        assertEquals("18/08/2026", result.get("due_date"));
    }

    @Test public void realChallengeStillStopsTheAutomation() {
        String blocked = "Access Denied\nError 15\nVerifique que voce e humano";
        IllegalStateException error = assertThrows(IllegalStateException.class,
            () -> EquatorialTextParser.parse(blocked));
        assertTrue(error.getMessage().contains("verificacao humana"));
    }
}
