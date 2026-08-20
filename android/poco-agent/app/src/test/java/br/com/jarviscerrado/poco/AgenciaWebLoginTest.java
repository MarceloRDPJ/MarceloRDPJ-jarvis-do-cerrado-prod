package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * Contrato do login da Agência Web ({@code go.*}).
 *
 * Nenhum dado real. O CPF usado tem dígitos verificadores válidos e é o valor
 * clássico de teste; a conta contrato é inventada.
 *
 * O que estes testes protegem: as regras abaixo foram lidas do fonte de
 * {@code auth-go.js} em produção, e cada uma delas, se adivinhada, falha em
 * silêncio — o portal responde a MESMA mensagem genérica para campo vazio,
 * credencial errada e antifraude reprovado, então um erro de mapeamento aqui
 * seria indistinguível de "a Equatorial recusou".
 */
public class AgenciaWebLoginTest {

    private static final String FAKE_CPF = "111.444.777-35";

    // ------------------------------------------------- documento

    @Test
    public void documentIsStrippedTheWayThePageStripsIt() {
        // O script remove ponto, hifen, barra e espaco, e sobe para maiusculas.
        assertEquals("11144477735", AgenciaWebLogin.document(FAKE_CPF));
        assertEquals("11144477735", AgenciaWebLogin.document(" 111 444 777 35 "));
        assertEquals("11222333000181", AgenciaWebLogin.document("11.222.333/0001-81"));
    }

    @Test
    public void alphanumericCnpjKeepsItsLetters() {
        // A linha que apagava todo nao-digito esta COMENTADA no fonte, e CNPJ
        // alfanumerico existe: apagar letra aqui viraria recusa inexplicavel.
        assertEquals("12ABC34501DE35", AgenciaWebLogin.document("12.ABC.345/01DE-35"));
        assertEquals("12ABC34501DE35", AgenciaWebLogin.document("12abc34501de35"));
    }

    @Test
    public void missingDocumentIsEmptyNotNull() {
        assertEquals("", AgenciaWebLogin.document(null));
        assertEquals("", AgenciaWebLogin.document(""));
    }

    // ------------------------------------------------- conta contrato

    @Test
    public void unitIsZeroPaddedToFifteen() {
        assertEquals("000012345678901", AgenciaWebLogin.unit("12345678901"));
        assertEquals(15, AgenciaWebLogin.unit("12345678901").length());
        // Separador vindo do cofre nao deve virar parte do identificador.
        assertEquals("000012345678901", AgenciaWebLogin.unit("123.456.789-01"));
    }

    @Test
    public void anAlreadyLongUnitIsNeverTruncated() {
        // Cortar identificador e consultar a conta de outra pessoa. Melhor o
        // portal recusar o valor do cofre do que o ROD acertar a conta errada.
        assertEquals("1234567890123456", AgenciaWebLogin.unit("1234567890123456"));
        assertEquals("123456789012345", AgenciaWebLogin.unit("123456789012345"));
    }

    @Test
    public void emptyUnitStaysEmptyInsteadOfBecomingFifteenZeros() {
        // Quinze zeros seriam um identificador de aparencia valida.
        assertEquals("", AgenciaWebLogin.unit(""));
        assertEquals("", AgenciaWebLogin.unit(null));
        assertEquals("", AgenciaWebLogin.unit("sem digito"));
    }

    // ------------------------------------------------- serviço

    @Test
    public void serviceComesFromTheSecondPathSegment() {
        assertEquals("emitir-segunda-via",
            AgenciaWebLogin.serviceFor("/sua-conta/emitir-segunda-via/"));
        assertEquals("fazer-reclamacao",
            AgenciaWebLogin.serviceFor("/sua-conta/fazer-reclamacao/"));
    }

    @Test
    public void theBarePortalHasNoServiceAndLandsOnTheLoggedHome() {
        assertEquals("", AgenciaWebLogin.serviceFor("/sua-conta/"));
        assertEquals("", AgenciaWebLogin.serviceFor("/sua-conta"));
        assertEquals("", AgenciaWebLogin.serviceFor("/"));
        assertEquals("", AgenciaWebLogin.serviceFor(null));
    }

    // ------------------------------------------------- prontidão

    @Test
    public void anIncompleteFormIsNotSent() {
        // Enviar vazio gasta uma das duas tentativas do job e volta com a
        // mesma mensagem de credencial errada: diagnostico envenenado.
        assertFalse(AgenciaWebLogin.ready("", "12345678901"));
        assertFalse(AgenciaWebLogin.ready(FAKE_CPF, ""));
        assertFalse(AgenciaWebLogin.ready(null, null));
        assertFalse(AgenciaWebLogin.ready("123", "12345678901"));
        assertTrue(AgenciaWebLogin.ready(FAKE_CPF, "12345678901"));
    }

    // ------------------------------------------------- desfecho

    @Test
    public void jwtIsTheProofOfSession() {
        assertEquals(AgenciaWebLogin.Outcome.AUTHENTICATED,
            AgenciaWebLogin.classify(true, false, false));
        // JWT vence erro na tela: o script so grava o token depois de um 200.
        assertEquals(AgenciaWebLogin.Outcome.AUTHENTICATED,
            AgenciaWebLogin.classify(true, true, true));
    }

    @Test
    public void aVisibleErrorBoxIsRefusalAndAHiddenOneIsNot() {
        assertEquals(AgenciaWebLogin.Outcome.REFUSED,
            AgenciaWebLogin.classify(false, true, true));
        // A caixa fica sempre no DOM; presenca nao e veredito.
        assertEquals(AgenciaWebLogin.Outcome.PENDING,
            AgenciaWebLogin.classify(false, false, true));
    }

    @Test
    public void noFormAndNoJwtIsNotAVerdict() {
        assertEquals(AgenciaWebLogin.Outcome.UNKNOWN,
            AgenciaWebLogin.classify(false, false, false));
    }

    // ------------------------------------------------- alvos proibidos

    @Test
    public void theDismissControlIsNotTheConsentControl() {
        // Fechar o aviso e consentir com ele nao sao a mesma acao, e o ROD nao
        // tem autorizacao para consentir em nome do proprietario.
        assertFalse(AgenciaWebLogin.LGPD_CLOSE.equals(AgenciaWebLogin.LGPD_ACCEPT));
        assertTrue(AgenciaWebLogin.LGPD_ACCEPT.contains("lgpd_accept"));
        assertFalse(AgenciaWebLogin.LGPD_CLOSE.contains("lgpd_accept"));
    }

    @Test
    public void theUnitGoesInTheFieldTheHandlerActuallyReads() {
        // O handler monta uc a partir do FormData 'senha'. Os campos
        // 'contrato-novo' e '#identificador-2' existem, estao invisiveis e nao
        // sao lidos: preencher aqueles manda a UC vazia com cara de completo.
        assertEquals("#senha-identificador", AgenciaWebLogin.FIELD_UNIT);
        assertEquals("#identificador", AgenciaWebLogin.FIELD_DOCUMENT);
    }
}
