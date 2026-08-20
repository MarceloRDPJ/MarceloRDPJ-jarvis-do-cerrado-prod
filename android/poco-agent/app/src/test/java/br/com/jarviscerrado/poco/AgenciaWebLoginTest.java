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
    // ------------------------------------------------- ponte entre os hosts

    @Test
    public void theBridgeIsOpenOnlyWithEveryBillControlPresent() {
        // Postback parcial do ASPX ja devolveu combo sem botao. Aceitar "quase"
        // como ponte aberta faria o ROD prometer consulta que nao completa.
        assertEquals(AgenciaWebLogin.BridgeState.OPEN, AgenciaWebLogin.bridge(
            true, false, true, true, true, true, true));
        assertEquals(AgenciaWebLogin.BridgeState.CLOSED, AgenciaWebLogin.bridge(
            true, false, true, true, true, false, true));
        assertEquals(AgenciaWebLogin.BridgeState.CLOSED, AgenciaWebLogin.bridge(
            true, false, false, true, true, true, true));
    }

    @Test
    public void aVisibleLoginFormMeansTheSessionDidNotCross() {
        // Se o cabecalho do ASPX volta a pedir credencial, a sessao do go.* nao
        // valeu ali — mesmo que a pagina tenha carregado inteira.
        assertEquals(AgenciaWebLogin.BridgeState.CLOSED, AgenciaWebLogin.bridge(
            true, true, true, true, true, true, true));
    }

    @Test
    public void aBlankBillPageIsItsOwnState() {
        // Sem sessao o SegundaVia.aspx volta EM BRANCO: nao oferece nem login.
        // Confundir isso com "fechado por credencial" mandaria o dono procurar
        // defeito no lugar errado.
        assertEquals(AgenciaWebLogin.BridgeState.BLANK, AgenciaWebLogin.bridge(
            true, false, false, false, false, false, false));
    }

    @Test
    public void withoutALoginOnGoThereIsNothingToMeasure() {
        // Medir a ponte sem ter autenticado seria concluir por coincidencia.
        assertEquals(AgenciaWebLogin.BridgeState.NOT_TESTED, AgenciaWebLogin.bridge(
            false, false, true, true, true, true, true));
    }

    @Test
    public void theServiceWordIsGenericSoTheLabelNeverLeaks() {
        // O menu autenticado costuma trazer o nome do titular no texto do link.
        // O que vai para a trilha e a palavra do vocabulario, nunca o rotulo.
        assertEquals("segunda via", AgenciaWebLogin.serviceWord("segunda via de fatura"));
        assertEquals("agencia virtual", AgenciaWebLogin.serviceWord("acesse a agencia virtual"));
        assertEquals("", AgenciaWebLogin.serviceWord("trabalhe conosco"));
        assertEquals("", AgenciaWebLogin.serviceWord(null));
    }

    @Test
    public void theBillHostIsTheAspxHostNotTheInstitutionalOne() {
        assertEquals("goias.equatorialenergia.com.br", AgenciaWebLogin.BILL_HOST);
        assertFalse(AgenciaWebLogin.LOGIN_URL.contains(AgenciaWebLogin.BILL_HOST));
    }

    // ------------------------------------------------- vocabulario do relatorio

    @Test
    public void anOpaqueRefusalIsReportedAsRefusalAndNothingMore() {
        // O auth-go.js escreve a MESMA mensagem para qualquer status != 200, e
        // por isso credencial errada e reCAPTCHA reprovado nao existem como
        // estados aqui: a pagina nao contem a informacao que os separaria.
        assertEquals(AgenciaWebLogin.GoOutcome.GO_LOGIN_REJECTED,
            AgenciaWebLogin.outcome(EquatorialSession.State.LOGIN_REFUSED_OPAQUE));
    }

    @Test
    public void bothProofsOfSessionCountAsLoginOk() {
        // JWT depois do envio e JWT achado ja na abertura provam a mesma coisa.
        assertEquals(AgenciaWebLogin.GoOutcome.GO_LOGIN_OK,
            AgenciaWebLogin.outcome(EquatorialSession.State.LOGIN_OK));
        assertEquals(AgenciaWebLogin.GoOutcome.GO_LOGIN_OK,
            AgenciaWebLogin.outcome(EquatorialSession.State.SESSION_VALID));
    }

    @Test
    public void noVerdictWithinTheDeadlineIsTimeoutNotRefusal() {
        // Chamar de recusa o que foi prazo curto culparia a Equatorial por um
        // defeito nosso.
        assertEquals(AgenciaWebLogin.GoOutcome.GO_TIMEOUT,
            AgenciaWebLogin.outcome(EquatorialSession.State.LOGIN_IN_PROGRESS));
        assertEquals(AgenciaWebLogin.GoOutcome.GO_PORTAL_ERROR,
            AgenciaWebLogin.outcome(EquatorialSession.State.BROWSER_STALE));
    }
    @Test
    public void theNoticeWordNamesTheRefusalWithoutCopyingThePage() {
        // O SegundaVia.aspx sem sessao nao devolve formulario de login: ele
        // redireciona para uma pagina curta. Guardar a PALAVRA do vocabulario
        // diz ao dono por que a area recusou sem levar texto de pagina para o log.
        assertEquals("suporte", AgenciaWebLogin.noticeWord("pagina de suporte"));
        assertEquals("sessao expirada", AgenciaWebLogin.noticeWord("sua sessao expirada"));
        assertEquals("", AgenciaWebLogin.noticeWord("segunda via emitida"));
        assertEquals("", AgenciaWebLogin.noticeWord(null));
    }

    @Test
    public void theNoticeVocabularyExpectsFoldedText() {
        // A comparacao roda sobre texto sem acento e em minusculas; palavra com
        // acento no vocabulario nunca casaria e o aviso viraria vazio silencioso.
        for (String word : AgenciaWebLogin.BILL_NOTICE_WORDS) {
            assertEquals(word, EquatorialSession.fold(word));
        }
        for (String word : AgenciaWebLogin.SERVICE_WORDS) {
            assertEquals(word, EquatorialSession.fold(word));
        }
    }
}
