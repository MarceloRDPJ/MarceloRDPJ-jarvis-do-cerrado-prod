package br.com.jarviscerrado.poco;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * A máquina de sessão aplicada à Agência Web, onde o marcador é estrutural.
 *
 * O que estes testes protegem: as duas invariantes de segurança continuam
 * valendo neste portal. Recusa opaca encerra o job em vez de virar segunda
 * tentativa às cegas, e o limite de duas tentativas segue de pé.
 */
public class AgenciaWebSessionTest {

    @Test
    public void jwtMeansSessionAliveWithoutReadingAnyText() {
        assertEquals(EquatorialSession.State.SESSION_VALID,
            EquatorialSession.classifyAgenciaWeb(true, false, false, true, false));
        assertEquals(EquatorialSession.State.LOGIN_OK,
            EquatorialSession.classifyAgenciaWeb(true, false, false, true, true));
    }

    @Test
    public void noJwtWithTheFormOnScreenIsAFallenSession() {
        assertEquals(EquatorialSession.State.SESSION_EXPIRED,
            EquatorialSession.classifyAgenciaWeb(false, false, true, true, false));
        assertEquals(EquatorialSession.State.LOGIN_IN_PROGRESS,
            EquatorialSession.classifyAgenciaWeb(false, false, true, true, true));
    }

    @Test
    public void aVisibleErrorCountsOnlyAfterSubmitting() {
        assertEquals(EquatorialSession.State.LOGIN_REFUSED_OPAQUE,
            EquatorialSession.classifyAgenciaWeb(false, true, true, true, true));
        // Antes do envio a caixa pode ter sobrado da tentativa anterior na aba.
        assertEquals(EquatorialSession.State.SESSION_EXPIRED,
            EquatorialSession.classifyAgenciaWeb(false, true, true, true, false));
    }

    @Test
    public void aDeadEngineIsNeverReadAsARefusal() {
        assertEquals(EquatorialSession.State.BROWSER_STALE,
            EquatorialSession.classifyAgenciaWeb(false, true, true, false, true));
    }

    @Test
    public void opaqueRefusalIsTerminalSoTheAccountIsNeverHammered() {
        EquatorialSession session = new EquatorialSession(true);
        EquatorialSession.Decision decision =
            session.observe(EquatorialSession.State.LOGIN_REFUSED_OPAQUE);
        assertEquals(EquatorialSession.Decision.FAIL_REFUSED_OPAQUE, decision);
        assertTrue(EquatorialSession.terminal(decision));
        assertEquals(0, session.loginAttempts());
    }

    @Test
    public void theOpaqueMessageBlamesNeitherTheVaultNorTheAntifraudAlone() {
        String message =
            EquatorialSession.errorFor(EquatorialSession.Decision.FAIL_REFUSED_OPAQUE);
        assertTrue(message.startsWith("EQUATORIAL_LOGIN_REFUSED"));
        // O dono precisa saber que ha duas causas possiveis; mandar conferir o
        // cofre quando o problema e o antifraude e mandar procurar no lugar
        // errado.
        assertTrue(message.contains("cofre"));
        assertTrue(message.contains("reCAPTCHA"));
    }

    @Test
    public void theTwoAttemptLimitStillHolds() {
        EquatorialSession session = new EquatorialSession(true);
        assertEquals(EquatorialSession.Decision.LOGIN,
            session.observe(EquatorialSession.State.SESSION_EXPIRED));
        assertEquals(EquatorialSession.Decision.LOGIN,
            session.observe(EquatorialSession.State.SESSION_EXPIRED));
        // A terceira observacao nao vira terceiro login.
        EquatorialSession.Decision third =
            session.observe(EquatorialSession.State.SESSION_EXPIRED);
        assertEquals(EquatorialSession.Decision.FALLBACK_WEBVIEW, third);
        assertEquals(EquatorialSession.MAX_LOGIN_ATTEMPTS, session.loginAttempts());
    }
}
