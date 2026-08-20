package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.Arrays;
import java.util.Collections;
import org.junit.Test;

/**
 * Identificacao da linha da fatura na tabela de segunda via.
 *
 * Nenhum dado real: as referencias sao meses genericos e os valores sao 1,00.
 *
 * O que estes testes protegem: enquanto houver uma unica fatura em aberto,
 * qualquer heuristica funciona. O erro aparece no primeiro mes com duas em
 * aberto — e ai entregar o Pix da linha errada e entregar a ordem de pagamento
 * errada, com aparencia de acerto.
 */
public class PixRowLocatorTest {

    @Test
    public void portalWritesTheReferenceTwoWaysAndBothNormalize() {
        assertEquals("08/2026", PixRowLocator.normalizeReference("08/2026"));
        assertEquals("08/2026", PixRowLocator.normalizeReference("AGO/2026"));
        assertEquals("08/2026", PixRowLocator.normalizeReference("ago-2026"));
        assertEquals("08/2026", PixRowLocator.normalizeReference("Mes/Ano de referencia: AGO/2026"));
        assertEquals("12/2025", PixRowLocator.normalizeReference("DEZ.2025"));
    }

    @Test
    public void whatIsNotAReferenceStaysEmpty() {
        assertEquals("", PixRowLocator.normalizeReference(""));
        assertEquals("", PixRowLocator.normalizeReference(null));
        assertEquals("", PixRowLocator.normalizeReference("R$ 1,00"));
        assertEquals("", PixRowLocator.normalizeReference("13/2026"));
        // Vencimento nao e referencia: dia/mes/ano tem tres blocos.
        assertEquals("", PixRowLocator.normalizeReference("15/09/2026"));
    }

    @Test
    public void matchesTheRowThatCarriesTheRequestedReference() {
        assertTrue(PixRowLocator.matchesReference("AGO/2026 R$ 1,00 Baixar PIX", "08/2026"));
        assertTrue(PixRowLocator.matchesReference("08/2026 R$ 1,00", "AGO/2026"));
        assertFalse(PixRowLocator.matchesReference("JUL/2026 R$ 1,00", "08/2026"));
        // Sem referencia pedida nao ha correspondencia: seria casar com qualquer linha.
        assertFalse(PixRowLocator.matchesReference("AGO/2026", ""));
    }

    // ------------------------------------------------------- indice da fatura

    @Test
    public void invoiceIndexFollowsTheOrderOfTheRows() {
        // Duas faturas em aberto, na ordem em que a arvore devolve os textos.
        java.util.List<String> page = Arrays.asList(
            "Mes/Ano de referencia", "Valor", "Download", "Pagamento via PIX",
            "JUL/2026", "R$ 1,00", "Baixar", "PIX",
            "AGO/2026", "R$ 1,00", "Baixar", "PIX");

        assertEquals(0, PixRowLocator.invoiceIndex(page, "07/2026"));
        assertEquals(1, PixRowLocator.invoiceIndex(page, "AGO/2026"));
        assertEquals(PixRowLocator.NOT_FOUND, PixRowLocator.invoiceIndex(page, "06/2026"));
    }

    @Test
    public void theSameReferenceWrittenTwiceInARowIsStillOneInvoice() {
        // O portal repete a referencia no titulo do link. Contar duas vezes
        // deslocaria o indice de todas as linhas seguintes.
        java.util.List<String> page = Arrays.asList(
            "JUL/2026", "Baixar fatura 07/2026", "PIX",
            "AGO/2026", "Baixar fatura 08/2026", "PIX");

        assertEquals(0, PixRowLocator.invoiceIndex(page, "07/2026"));
        assertEquals(1, PixRowLocator.invoiceIndex(page, "08/2026"));
    }

    @Test
    public void withoutARequestOnlyASingleInvoiceIsUnambiguous() {
        assertEquals(0, PixRowLocator.invoiceIndex(Arrays.asList("AGO/2026", "R$ 1,00"), ""));
        assertEquals(PixRowLocator.AMBIGUOUS,
            PixRowLocator.invoiceIndex(Arrays.asList("JUL/2026", "AGO/2026"), ""));
        assertEquals(PixRowLocator.NOT_FOUND,
            PixRowLocator.invoiceIndex(Collections.<String>emptyList(), ""));
    }

    @Test
    public void picksThePixControlAmongTheControlsOfTheRow() {
        // Ordem das colunas: download e pagamento via PIX.
        assertEquals(1, PixRowLocator.preferPixLabel(Arrays.asList("Baixar", "Pagamento via PIX")));
        // Sem rótulo reconhecível a decisão sai daqui e vai para a geometria.
        assertEquals(PixRowLocator.NOT_FOUND, PixRowLocator.preferPixLabel(Arrays.asList("", "")));
        // Dois controles de Pix na mesma linha significam leitura errada da linha.
        assertEquals(PixRowLocator.AMBIGUOUS,
            PixRowLocator.preferPixLabel(Arrays.asList("PIX", "Pagar com pix")));
        assertEquals(PixRowLocator.NOT_FOUND, PixRowLocator.preferPixLabel(null));
    }

    @Test
    public void recognizesThePixControlOfTheRow() {
        assertTrue(PixRowLocator.isPixControl("Pagamento via PIX"));
        assertTrue(PixRowLocator.isPixControl("pix"));
        assertTrue(PixRowLocator.isPixControl("Ver QR Code"));
        assertFalse(PixRowLocator.isPixControl("Download"));
        assertFalse(PixRowLocator.isPixControl(null));
    }
}
