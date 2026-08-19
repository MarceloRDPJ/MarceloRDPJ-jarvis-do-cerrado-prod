package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import br.com.jarviscerrado.poco.JarvisAccessibilityService.ContractMatch;
import org.junit.Test;

/**
 * Regras de identificação do imóvel no seletor da Equatorial.
 *
 * Todos os números aqui são SINTÉTICOS (sequências óbvias, blocos repetidos).
 * Nenhuma unidade consumidora real aparece neste arquivo.
 *
 * O que estes testes protegem: em produção nenhuma das 16 consultas completou, e
 * a causa raiz não era leitura, era seleção. Casar por substring clicava o imóvel
 * errado; tocar num item fora da janela visível acertava outro ponto da tela. Nos
 * dois casos `dispatchGesture` devolvia true e o passo era dado como bem-sucedido.
 */
public class EquatorialContractTest {

    // ------------------------------------------------- casamento por número

    @Test
    public void exactNumberMatchesEvenSurroundedByLabels() {
        // Como o portal escreve a linha do contrato: rótulo, número e endereço.
        assertTrue(ContractMatch.matches("Conta contrato 87654321 - Rua Ficticia", "87654321"));
        assertTrue(ContractMatch.matches("UC: 87654321", "87654321"));
        assertTrue(ContractMatch.matches("87654321", "87654321"));
    }

    @Test
    public void longerNumberContainingTheExpectedOneIsRejected() {
        // O defeito comprovado: `digits(text).contains(expected)` aceitava isto e
        // clicava no imóvel vizinho da lista.
        assertFalse(ContractMatch.matches("Conta contrato 876543210", "87654321"));
        assertFalse(ContractMatch.matches("Conta contrato 187654321", "87654321"));
        assertFalse(ContractMatch.matches("1876543219", "87654321"));
    }

    @Test
    public void shorterNumberIsNotAcceptedForALongerExpectation() {
        assertFalse(ContractMatch.matches("Conta contrato 8765432", "87654321"));
    }

    @Test
    public void separatorsInsideTheSameNumberDoNotBreakTheMatch() {
        // A mesma conta contrato aparece agrupada na lista e corrida no cofre.
        assertTrue(ContractMatch.matches("8765 4321", "87654321"));
        assertTrue(ContractMatch.matches("8.765.432-1", "87654321"));
        assertTrue(ContractMatch.matches(" 8765 4321 ", "87654321"));
    }

    @Test
    public void lettersAndCommasSeparateDifferentNumbers() {
        // "8765" e "4321" são dois números distintos na mesma linha: juntá-los
        // fabricaria uma correspondência que a tela não tem.
        assertFalse(ContractMatch.matches("8765 kWh e 4321 reais", "87654321"));
        assertFalse(ContractMatch.matches("8765,4321", "87654321"));
    }

    @Test
    public void leadingZerosAreIrrelevantOnBothSides() {
        assertTrue(ContractMatch.matches("Contrato 0087654321", "87654321"));
        assertTrue(ContractMatch.matches("Contrato 87654321", "0087654321"));
    }

    @Test
    public void withoutAnExpectedNumberNothingMatches() {
        // Sem imóvel configurado não se escolhe nada: atribuir a fatura ao imóvel
        // errado é pior do que falhar com código.
        assertFalse(ContractMatch.matches("Conta contrato 87654321", ""));
        assertFalse(ContractMatch.matches("Conta contrato 87654321", null));
        assertFalse(ContractMatch.matches("Conta contrato 87654321", "sem digito"));
        assertFalse(ContractMatch.matches(null, "87654321"));
        assertFalse(ContractMatch.matches("nenhum numero aqui", "87654321"));
    }

    @Test
    public void normalizeKeepsTheOldDigitsSemantics() {
        // `digits` passou a delegar aqui; o fluxo da Saneago depende deste
        // comportamento exato (só dígitos, sem zeros à esquerda, "0" preservado).
        assertEquals("", ContractMatch.normalize(null));
        assertEquals("", ContractMatch.normalize("abc"));
        assertEquals("0", ContractMatch.normalize("000"));
        assertEquals("12345", ContractMatch.normalize("Conta: 012.345"));
    }

    // ------------------------------------------------------- visibilidade

    @Test
    public void centerInsideTheWindowIsClickable() {
        assertTrue(ContractMatch.centerInside(100, 500, 900, 600, 0, 200, 1000, 1800));
    }

    @Test
    public void itemScrolledOutOfTheWindowIsRejected() {
        // Item rolado para fora tem bounds não-vazio; o toque no centro cairia
        // abaixo da lista, em qualquer outra coisa que estivesse ali.
        assertFalse(ContractMatch.centerInside(100, 1900, 900, 2000, 0, 200, 1000, 1800));
        assertFalse(ContractMatch.centerInside(100, 20, 900, 120, 0, 200, 1000, 1800));
    }

    @Test
    public void degenerateBoundsAreRejected() {
        assertFalse(ContractMatch.centerInside(0, 0, 0, 0, 0, 0, 1000, 1800));
        assertFalse(ContractMatch.centerInside(500, 500, 500, 900, 0, 0, 1000, 1800));
    }

    @Test
    public void bordersOfTheWindowStillCount() {
        assertTrue(ContractMatch.centerInside(0, 0, 2000, 400, 0, 200, 1000, 1800));
    }

    // ------------------------------------------------ orçamento de tela

    @Test
    public void screenBudgetCoversEveryStepAtItsFullTimeout() {
        // 180 s não cobriam 4 chamadas de 60 s: o wake lock caía antes do fim e a
        // leitura falhava por tela apagada, não por portal.
        assertTrue(EquatorialReader.SCREEN_BUDGET_MILLIS
            >= EquatorialReader.CALL_TIMEOUT_MILLIS * EquatorialReader.FLOW_STEPS);
        assertEquals(250_000L, EquatorialReader.screenBudget(50_000L, 4, 50_000L));
    }
}
