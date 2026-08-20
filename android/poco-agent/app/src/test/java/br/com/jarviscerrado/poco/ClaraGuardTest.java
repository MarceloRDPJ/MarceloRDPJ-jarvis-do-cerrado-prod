package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * Fronteira de autorizacao do canal Clara.
 *
 * Nenhum dado real. O unico numero verdadeiro e o destino publico da
 * concessionaria, que ja e publicado pela propria Equatorial; todo numero
 * "errado" abaixo e inventado.
 *
 * O que estes testes protegem: o destino autorizado e um so, e mensagem em nome
 * do dono para o numero errado nao tem desfazer. E acionar rotulo de transacao
 * por engano nao e consulta que falhou, e ordem de pagamento que funcionou.
 */
public class ClaraGuardTest {

    // ------------------------------------------------------- destinatario

    @Test
    public void theAuthorizedNumberIsAcceptedInTheFormsTheScreenUses() {
        assertTrue(ClaraGuard.isAuthorizedDestination("+556232432020"));
        assertTrue(ClaraGuard.isAuthorizedDestination("+55 62 3243-2020"));
        assertTrue(ClaraGuard.isAuthorizedDestination("+55 (62) 3243 2020"));
        assertTrue(ClaraGuard.isAuthorizedDestination("556232432020"));
        // Discagem internacional escrita com 00 no lugar do sinal.
        assertTrue(ClaraGuard.isAuthorizedDestination("00556232432020"));
        // Sufixo de interface nao carrega digito e nao deve estorvar.
        assertTrue(ClaraGuard.isAuthorizedDestination("+55 62 3243-2020 online"));
    }

    @Test
    public void oneDigitOffIsAnotherPersonAndIsRefused() {
        assertFalse(ClaraGuard.isAuthorizedDestination("+556232432021"));
        assertFalse(ClaraGuard.isAuthorizedDestination("+556232432O20"));
        // Prefixo e sufixo: conter o autorizado nao e ser o autorizado.
        assertFalse(ClaraGuard.isAuthorizedDestination("+5562324320201"));
        assertFalse(ClaraGuard.isAuthorizedDestination("+1556232432020"));
    }

    @Test
    public void aNameIsNotProofOfDestination() {
        // Contato salvo pode apontar para qualquer numero: sem digito, sem envio.
        assertFalse(ClaraGuard.isAuthorizedDestination("Clara"));
        assertFalse(ClaraGuard.isAuthorizedDestination("Equatorial Goias"));
        assertFalse(ClaraGuard.isAuthorizedDestination("Clara - Equatorial"));
        assertFalse(ClaraGuard.isAuthorizedDestination(""));
        assertFalse(ClaraGuard.isAuthorizedDestination(null));
        assertEquals("", ClaraGuard.normalizeDestination("Clara"));
    }

    @Test
    public void localFormWithoutCountryStaysAmbiguousAndIsRefused() {
        assertFalse(ClaraGuard.isAuthorizedDestination("(62) 3243-2020"));
        assertFalse(ClaraGuard.isAuthorizedDestination("3243-2020"));
    }

    @Test
    public void groupTitleCarriesAnExtraDigitAndFallsOut() {
        // Grupo nao e o canal autorizado; a contagem no titulo entrega o grupo.
        assertFalse(ClaraGuard.isAuthorizedDestination("+55 62 3243-2020 e mais 3"));
        assertFalse(ClaraGuard.isAuthorizedDestination("+55 62 3243-2020, +55 62 99999-1111"));
    }

    // ------------------------------------------------------- envio

    @Test
    public void onlyTheOfficialOpeningsCanBeSent() {
        assertTrue(ClaraGuard.outboundAllowed("Ola"));
        assertTrue(ClaraGuard.outboundAllowed(
            "Olá, gostaria de solicitar o código para pagamento de faturas"));
        assertTrue(ClaraGuard.outboundAllowed("Código de barras para pagamento"));
        assertTrue(ClaraGuard.outboundAllowed("SEGUNDA VIA"));
    }

    @Test
    public void anythingNotAuthorizedIsRefusedEvenWhenHarmless() {
        // Lista fechada: o default e recusar, nao procurar motivo para recusar.
        assertFalse(ClaraGuard.outboundAllowed("bom dia, tudo bem?"));
        assertFalse(ClaraGuard.outboundAllowed(""));
        assertFalse(ClaraGuard.outboundAllowed(null));
        assertFalse(ClaraGuard.outboundAllowed("Ola, quero pagar a fatura"));
    }

    @Test
    public void secretsAndPayloadsAreNeverSendable() {
        assertFalse(ClaraGuard.outboundAllowed("000201265802BR5913FULANO DE TAL6009SAO PAULO"));
        assertFalse(ClaraGuard.outboundAllowed("minha senha e 1234"));
        assertFalse(ClaraGuard.outboundAllowed("00000000-0000-0000-0000-000000000000"));
    }

    // ------------------------------------------------------- toque

    @Test
    public void consultationLabelsAreTappable() {
        assertTrue(ClaraGuard.tapAllowed("Segunda via"));
        assertTrue(ClaraGuard.tapAllowed("Código de barras"));
        assertTrue(ClaraGuard.tapAllowed("Codigo Pix"));
        assertTrue(ClaraGuard.tapAllowed("Consultar débito"));
        assertTrue(ClaraGuard.tapAllowed("  MENU   PRINCIPAL  "));
    }

    @Test
    public void transactionLabelsAreRefused() {
        assertFalse(ClaraGuard.tapAllowed("Pagar Agora"));
        assertFalse(ClaraGuard.tapAllowed("Pagar com Pix"));
        assertFalse(ClaraGuard.tapAllowed("Negociar dívida"));
        assertFalse(ClaraGuard.tapAllowed("Parcelamento"));
        assertFalse(ClaraGuard.tapAllowed("Religar energia"));
        assertFalse(ClaraGuard.tapAllowed("Aceitar débito automático"));
        assertFalse(ClaraGuard.tapAllowed("Atualizar cadastro"));
        assertFalse(ClaraGuard.tapAllowed("Informar cartão de crédito"));
    }

    @Test
    public void aForbiddenMarkerInsideAnAllowedLabelStillLoses() {
        // O motivo de a lista de proibidos existir alem da lista fechada.
        assertFalse(ClaraGuard.tapAllowed("Segunda via - Pagar Agora"));
        assertFalse(ClaraGuard.tapAllowed("Código de barras e pagar com cartão de crédito"));
    }

    @Test
    public void unknownLabelsAreRefusedRatherThanGuessed() {
        assertFalse(ClaraGuard.tapAllowed("Continuar"));
        assertFalse(ClaraGuard.tapAllowed("Sim"));
        assertFalse(ClaraGuard.tapAllowed("Clique aqui"));
        assertFalse(ClaraGuard.tapAllowed(""));
        assertFalse(ClaraGuard.tapAllowed(null));
    }

    // ------------------------------------------------------- mensagem inesperada

    @Test
    public void unexpectedPaymentTalkIsRecognized() {
        assertTrue(ClaraGuard.transactional("Quer pagar agora com desconto?"));
        assertTrue(ClaraGuard.transactional("Podemos negociar sua dívida em 12x"));
        assertTrue(ClaraGuard.transactional("Toque para abrir o app do banco"));
        assertTrue(ClaraGuard.transactional("Informar cartão de débito"));
    }

    @Test
    public void plainDataIsNotTransactional() {
        assertFalse(ClaraGuard.transactional("Sua fatura de 08/2026 vence em 15/09/2026"));
        assertFalse(ClaraGuard.transactional("Valor: R$ 1,00"));
        assertFalse(ClaraGuard.transactional(""));
        assertFalse(ClaraGuard.transactional(null));
    }
}
