package br.com.jarviscerrado.poco;

/**
 * Contrato do login da Agência Web da Equatorial (host {@code go.*}).
 *
 * Este é um portal DIFERENTE do {@code LoginGO.aspx} do host {@code goias.*}.
 * O ASPX é guardado pelo Transmit Security DRS, que recusou a automação em
 * silêncio; aqui não há DRS nenhum — o portão é reCAPTCHA v3 do Google, por
 * pontuação. São gates distintos, e o resultado de um não prediz o do outro.
 *
 * A classe é pura e sem Android de propósito: tudo que ela contém foi lido do
 * DOM e do código-fonte de {@code auth-go.js} em produção, e é justamente a
 * parte que erra silenciosamente se for adivinhada. Quem dirige a página é o
 * motor; quem sabe COMO a página funciona é este arquivo.
 *
 * O que o {@code auth-go.js} faz, na ordem, conferido no fonte:
 *
 * <ol>
 *   <li>intercepta o submit do formulário {@code #login-box-form-go};</li>
 *   <li>chama {@code grecaptcha.execute(siteKey, {action:'login'})} e espera o
 *       token — o token é produzido pela PRÓPRIA página;</li>
 *   <li>monta {@code {documento, uc, service}} a partir do FormData;</li>
 *   <li>faz POST para {@code {site_base_url}/ajax-requests/ajax-auth-go} com os
 *       cabeçalhos {@code X-Recaptcha-Response} e {@code X-Recaptcha-Action};</li>
 *   <li>se 200, grava o JWT em {@code localStorage.jwt} e navega para
 *       {@code /sua-conta/{service}};</li>
 *   <li>se não-200, mostra a mensagem genérica de código {@code #gh678}.</li>
 * </ol>
 *
 * REGRA QUE NÃO NEGOCIA: o ROD aciona o botão visível e deixa o reCAPTCHA da
 * página produzir o token. Nunca fabricar, montar ou repetir token, e nunca
 * chamar o endpoint direto. Se a pontuação recusar, é recusa legítima e o
 * proprietário é avisado — foi o que fizemos com o DRS.
 */
final class AgenciaWebLogin {

    /** Página que hospeda o formulário do titular. */
    static final String LOGIN_URL = "https://go.equatorialenergia.com.br/sua-conta/";

    /** Área logada, para onde o script navega quando não há serviço no caminho. */
    static final String ACCOUNT_URL = "https://go.equatorialenergia.com.br/sua-conta";

    /**
     * Endpoint do login, apenas para RECONHECER a resposta na trilha de rede.
     *
     * Não é para ser chamado. Está aqui para o motor saber qual requisição
     * observar, e porque documentar o alvo proibido é mais seguro do que deixar
     * a próxima pessoa descobri-lo sozinha.
     */
    static final String AUTH_ENDPOINT_PATH = "/ajax-requests/ajax-auth-go";

    static final String FORM = "#login-box-form-go";

    /** CPF/CNPJ do titular. Campo VISÍVEL do formulário. */
    static final String FIELD_DOCUMENT = "#identificador";

    /**
     * Unidade consumidora — e o nome do campo é {@code senha}, não {@code uc}.
     *
     * Custou uma leitura do fonte descobrir. O {@code auth-go.js} monta o JSON
     * com {@code uc: data.get('senha')}, ou seja, a UC entra por
     * {@code #senha-identificador}. Os campos {@code #identificador-conta-contrato}
     * ({@code name=contrato-novo}) e {@code #identificador-2} existem no HTML,
     * estão INVISÍVEIS e NÃO são lidos por este handler: preencher aqueles
     * mandaria a UC vazia com aparência de formulário completo.
     */
    static final String FIELD_UNIT = "#senha-identificador";

    /** Serviço de destino; o script preenche a partir do caminho da URL. */
    static final String FIELD_SERVICE = "#service-login";

    /** Botão de submit do formulário do titular ({@code name=envia-dados}). */
    static final String SUBMIT = "#login-box-form-go button[type=submit]";

    /** Caixa onde o script escreve a falha genérica. */
    static final String ERROR_BOX = "#error-message-login";

    /**
     * Fecha o aviso de LGPD SEM enviar nada.
     *
     * O outro botão do mesmo aviso é {@code #lgpd_accept}, rotulado "Enviar", e
     * ele SUBMETE o formulário de consentimento. Fechar e consentir não são a
     * mesma ação, e o ROD não tem autorização para consentir em nome do
     * proprietário — então o alvo é o "Fechar", nunca o "Enviar".
     */
    static final String LGPD_CLOSE = "button.btn-close.lgpd-btn-close";

    /** Botão de consentimento do aviso de LGPD. Nunca acionar. */
    static final String LGPD_ACCEPT = "#lgpd_accept";

    /** Marcador estrutural de sessão viva: o script guarda o JWT aqui. */
    static final String JWT_KEY = "jwt";

    /** Código da falha genérica do portal, presente na mensagem ao usuário. */
    static final String GENERIC_FAILURE_CODE = "#gh678";

    /** Comprimento da conta contrato aceito pelo portal. */
    static final int UNIT_LENGTH = 15;

    private AgenciaWebLogin() { }

    /** Como o formulário terminou, do ponto de vista de quem olhou a página. */
    enum Outcome {
        /** JWT presente: autenticado. Marcador estrutural, não texto. */
        AUTHENTICATED,
        /**
         * O portal recusou e não disse por quê.
         *
         * Credencial errada e pontuação de reCAPTCHA reprovada produzem
         * EXATAMENTE a mesma mensagem {@code #gh678}, porque o script escreve
         * o mesmo texto para qualquer status diferente de 200. Distinguir os
         * dois exige o status HTTP da resposta, que só a trilha de rede tem.
         */
        REFUSED,
        /** Ainda sem veredito: nem JWT, nem erro, formulário ainda na tela. */
        PENDING,
        /** A página não é a do formulário nem a área logada. */
        UNKNOWN
    }

    /**
     * Traduz a observação da página em desfecho.
     *
     * A ordem importa: JWT vem primeiro porque é estrutural. A caixa de erro
     * fica no DOM sempre, visível ou não, então presença não é veredito —
     * quem decide é estar visível.
     */
    static Outcome classify(boolean jwtPresent, boolean errorVisible, boolean loginFormPresent) {
        if (jwtPresent) return Outcome.AUTHENTICATED;
        if (errorVisible) return Outcome.REFUSED;
        if (loginFormPresent) return Outcome.PENDING;
        return Outcome.UNKNOWN;
    }

    /**
     * Normaliza o documento como o próprio {@code auth-go.js} normaliza.
     *
     * O script remove ponto, hífen, barra e espaço, e passa para maiúsculas —
     * e a linha que removia todo não-dígito está COMENTADA no fonte. A
     * diferença não é cosmética: CNPJ alfanumérico existe desde 2026, e um
     * {@code replaceAll("\\D","")} apagaria as letras e transformaria um
     * documento válido em recusa inexplicável.
     */
    static String document(String raw) {
        if (raw == null) return "";
        return raw.replaceAll("[.\\-/\\s]", "").toUpperCase();
    }

    /**
     * Conta contrato no formato que o portal espera: dígitos à direita,
     * zeros à esquerda até {@link #UNIT_LENGTH}.
     *
     * Uma unidade já mais longa que o limite volta inalterada em vez de ser
     * cortada: truncar identificador é inventar outra conta, e é melhor o
     * portal recusar um valor que veio do cofre do que o ROD consultar a conta
     * de outra pessoa.
     */
    static String unit(String raw) {
        String digits = raw == null ? "" : raw.replaceAll("\\D", "");
        if (digits.isEmpty()) return "";
        if (digits.length() >= UNIT_LENGTH) return digits;
        StringBuilder padded = new StringBuilder(UNIT_LENGTH);
        for (int i = digits.length(); i < UNIT_LENGTH; i++) padded.append('0');
        return padded.append(digits).toString();
    }

    /**
     * O serviço de destino, derivado do caminho como o script deriva.
     *
     * O script usa o segundo segmento do caminho, e o campo oculto decide para
     * onde a navegação vai DEPOIS do login. Carregar {@code /sua-conta/} deixa
     * o serviço vazio e cai na home da área logada; carregar a rota do serviço
     * leva direto a ela, poupando um passo de navegação autenticada.
     */
    static String serviceFor(String path) {
        if (path == null) return "";
        String[] parts = path.split("/");
        int seen = 0;
        for (String part : parts) {
            if (part.isEmpty()) continue;
            seen++;
            if (seen == 2) return part;
        }
        return "";
    }

    /**
     * O formulário está pronto para envio?
     *
     * Enviar com campo vazio gasta uma das duas tentativas do job e volta com a
     * mesma mensagem genérica de credencial errada — indistinguível de recusa
     * real. Conferir antes é o que mantém o diagnóstico honesto.
     */
    static boolean ready(String documentValue, String unitValue) {
        return document(documentValue).length() >= 11
            && unit(unitValue).length() == UNIT_LENGTH;
    }
}
