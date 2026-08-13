package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertEquals;
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
}
