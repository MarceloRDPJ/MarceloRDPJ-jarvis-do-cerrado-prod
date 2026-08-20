package br.com.jarviscerrado.poco;

import java.util.Arrays;
import java.util.List;

/**
 * Fronteira de autorizacao do canal Clara (WhatsApp da Equatorial Goias).
 *
 * O proprietario autorizou mensagem automatizada em nome dele para UM destino e
 * para UM proposito: consultar debito, segunda via, codigo de pagamento e Pix.
 * Nada aqui conversa com a Clara nem conhece a arvore de menus dela — isto e
 * so o portao. Existe separado porque a autorizacao do dono nao muda quando a
 * Clara muda de menu, e nao deve ser reescrita as pressas junto com o driver.
 *
 * Duas regras que dao razao de existir ao arquivo:
 *
 * 1. Numero errado e mensagem em nome do dono para um estranho. Um chat aberto
 *    no aparelho nao e prova de destinatario, e nome de contato salvo tambem
 *    nao: "Equatorial" na agenda pode apontar para qualquer numero. So digito
 *    conferido conta.
 * 2. Rotulo de transacao acionado por engano e ordem de pagamento. Consultar e
 *    reversivel; pagar, negociar, parcelar e religar nao sao. O ROD consulta.
 *
 * Nada de conteudo de conversa entra em log: os metodos devolvem decisao, e a
 * trilha registra a decisao, nunca o texto julgado.
 */
final class ClaraGuard {

    /** Unico destino autorizado, publicado pela propria Equatorial Goias. */
    static final String AUTHORIZED_DESTINATION = "+556232432020";

    /** Digitos do destino autorizado, em E.164 sem o sinal. */
    private static final String AUTHORIZED_DIGITS = "556232432020";

    /**
     * Textos que o ROD pode enviar. Lista fechada, nao filtro.
     *
     * Filtro proibe o que se lembrou de proibir; lista fechada recusa tudo que
     * nao foi autorizado, inclusive o que ninguem imaginou. Em mensagem enviada
     * em nome do dono, o default tem que ser recusar.
     */
    private static final List<String> ALLOWED_OUTBOUND = Arrays.asList(
        "ola",
        "ola, gostaria de solicitar o codigo para pagamento de faturas",
        "codigo de barras para pagamento",
        "segunda via",
        "codigo pix");

    /**
     * Rotulos que o ROD pode acionar na conversa.
     *
     * Tambem lista fechada, pela mesma razao. "Pagar Agora" nao esta aqui — e
     * nem precisaria estar na lista de proibidos para ser recusado.
     */
    private static final List<String> ALLOWED_TAP = Arrays.asList(
        "segunda via",
        "segunda via de fatura",
        "codigo de barras",
        "codigo de barras para pagamento",
        "codigo para pagamento",
        "codigo pix",
        "pix copia e cola",
        "copia e cola",
        "consultar debito",
        "consultar debitos",
        "debitos",
        "faturas",
        "minhas faturas",
        "voltar",
        "menu",
        "menu principal");

    /**
     * Rotulos que iniciam transacao ou alteram cadastro.
     *
     * Redundante de proposito. A lista fechada acima ja recusaria todos, mas um
     * rotulo proibido que aparece dentro de um permitido ("Segunda via - Pagar
     * Agora") passaria por igualdade e nao passa por aqui. Recusar duas vezes
     * custa nada; recusar de menos custa um pagamento.
     */
    private static final List<String> FORBIDDEN_MARKERS = Arrays.asList(
        "pagar agora",
        "pagar com",
        "pagar fatura",
        "quero pagar",
        "confirmar pagamento",
        "confirmar pix",
        "confirmar boleto",
        "ir para o banco",
        "abrir banco",
        "abrir o app do banco",
        "negociar",
        "negociacao",
        "parcelar",
        "parcelamento",
        "acordo",
        "entrada de",
        "religar",
        "religacao",
        "religamento",
        "debito automatico",
        "alterar cadastro",
        "atualizar cadastro",
        "cartao de credito",
        "cartao de debito",
        "informar cartao",
        "aceito",
        "aceitar",
        "contratar",
        "assinar");

    private ClaraGuard() { }

    /**
     * Digitos do destinatario mostrado na tela, ou vazio quando nao ha prova.
     *
     * Descarta tudo que nao e digito: separador, sinal e sufixo de interface
     * ("online", "visto por ultimo") somem sem afetar a comparacao. O efeito
     * colateral desejado e que titulo de grupo caia fora: "+55 62 3243-2020 e
     * mais 3" carrega um digito extra e deixa de casar, que e a resposta certa
     * — grupo nao e o canal autorizado.
     *
     * Forma local sem pais e recusada por ambiguidade: 6232432020 nao diz que
     * pais e, e adivinhar o pais de um destino autorizado seria adivinhar a
     * autorizacao.
     */
    static String normalizeDestination(String rendered) {
        if (rendered == null) return "";
        String digits = rendered.replaceAll("\\D", "");
        if (digits.isEmpty()) return "";
        // Discagem internacional escrita como 00 no lugar do sinal.
        if (digits.startsWith("00")) digits = digits.substring(2);
        return digits;
    }

    /**
     * Verdadeiro somente para o destino autorizado, por igualdade exata.
     *
     * Igualdade, nao prefixo nem "contem": 5562324320201 contem o autorizado e
     * e outro numero, e um digito a mais e outra pessoa recebendo mensagem em
     * nome do dono.
     */
    static boolean isAuthorizedDestination(String rendered) {
        return AUTHORIZED_DIGITS.equals(normalizeDestination(rendered));
    }

    /** Texto que o ROD pode enviar para a Clara. */
    static boolean outboundAllowed(String message) {
        String normalized = normalize(message);
        if (normalized.isEmpty()) return false;
        if (containsForbidden(normalized)) return false;
        return ALLOWED_OUTBOUND.contains(normalized);
    }

    /** Rotulo que o ROD pode acionar na conversa. */
    static boolean tapAllowed(String label) {
        String normalized = normalize(label);
        if (normalized.isEmpty()) return false;
        if (containsForbidden(normalized)) return false;
        return ALLOWED_TAP.contains(normalized);
    }

    /**
     * Marca de transacao em qualquer lugar do texto.
     *
     * Serve tambem para reconhecer mensagem inesperada de pagamento, oferta ou
     * link bancario, a qual o ROD nao responde.
     */
    static boolean transactional(String text) {
        return containsForbidden(normalize(text));
    }

    private static boolean containsForbidden(String normalized) {
        for (String marker : FORBIDDEN_MARKERS) if (normalized.contains(marker)) return true;
        return false;
    }

    /**
     * Minusculas, sem acento e com espaco unico.
     *
     * A Clara escreve "Segunda Via", "SEGUNDA VIA" e "Segunda via" na mesma
     * conversa, e comparar sem normalizar transformaria diferenca de maiuscula
     * em recusa — o que empurraria o driver para coordenada fixa, que e pior.
     */
    private static String normalize(String value) {
        if (value == null) return "";
        String lower = value.toLowerCase();
        StringBuilder folded = new StringBuilder(lower.length());
        for (int i = 0; i < lower.length(); i++) folded.append(fold(lower.charAt(i)));
        return folded.toString().replaceAll("\\s+", " ").trim();
    }

    /**
     * Dobra acento do portugues sem depender de java.text no Android.
     *
     * O arquivo e UTF-8, como os outros deste pacote que ja carregam acento em
     * literal. O teste cobre um rotulo acentuado de proposito: se algum dia a
     * compilacao passar a decodificar a fonte com outro encoding, a dobra para
     * de casar e o teste avisa, em vez de virar recusa silenciosa na frente da
     * Clara.
     */
    private static char fold(char value) {
        switch (value) {
            case 'á': case 'à': case 'â': case 'ã': case 'ä': return 'a';
            case 'é': case 'è': case 'ê': case 'ë': return 'e';
            case 'í': case 'ì': case 'î': case 'ï': return 'i';
            case 'ó': case 'ò': case 'ô': case 'õ': case 'ö': return 'o';
            case 'ú': case 'ù': case 'û': case 'ü': return 'u';
            case 'ç': return 'c';
            default: return value;
        }
    }
}
