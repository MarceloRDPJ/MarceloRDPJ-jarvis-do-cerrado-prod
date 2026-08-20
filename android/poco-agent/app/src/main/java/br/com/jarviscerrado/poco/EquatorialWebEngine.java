package br.com.jarviscerrado.poco;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Segundo motor de leitura: WebView do próprio ROD, com sessão só dele.
 *
 * O motor principal usa o Chrome do aparelho, e por isso não pode limpar nada:
 * apagar cookies lá derrubaria a sessão de todos os outros sites do proprietário.
 * Aqui a situação é oposta. Este WebView tem cookie jar próprio, cache próprio e
 * nenhum outro site dentro, então limpar é a recuperação correta e não custa nada
 * a ninguém: a limpeza feita antes de cada autenticação alcança exclusivamente o
 * que este arquivo criou.
 *
 * Ele existe como alternativa, não como substituto: entra quando o Chrome fica em
 * estado ruim ou quando a reautenticação por acessibilidade não fecha. Vantagem
 * real: DOM em vez de árvore de acessibilidade, o que elimina gesto, diálogo
 * nativo e elemento abaixo da dobra. Desvantagem real: o portal vê um user agent
 * de WebView, e um WAF pode responder com desafio — nesse caso o resultado é o
 * erro tipado de verificação humana, e nunca uma tentativa de contornar.
 *
 * Nada de conteúdo de página entra em log: só passo, presença e contagem.
 */
final class EquatorialWebEngine {

    static final String LOGIN_URL = "https://goias.equatorialenergia.com.br/LoginGO.aspx";
    static final String BILL_URL =
        "https://goias.equatorialenergia.com.br/AgenciaGO/Servi%C3%A7os/aberto/SegundaVia.aspx";
    /** Sem janela real: o WebView precisa de um tamanho para dispor o layout. */
    private static final int VIEWPORT_WIDTH = 1080;
    private static final int VIEWPORT_HEIGHT = 1920;
    /** Prazo de um evaluateJavascript. Se estourar, o motor está travado, não lento. */
    private static final long EVAL_TIMEOUT_MILLIS = 8_000L;
    /** Prazo para uma navegação assentar em readyState complete. */
    private static final long LOAD_TIMEOUT_MILLIS = 30_000L;
    private static final long POLL_MILLIS = 400L;
    /** Prazo do veredito do login: o portal gera o token de risco antes de enviar. */
    private static final long LOGIN_WAIT_MILLIS = 30_000L;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final AtomicBoolean failed = new AtomicBoolean(false);
    /** Quantas paginas terminaram de carregar. E o que distingue "outra pagina" de "a mesma". */
    private final AtomicInteger loads = new AtomicInteger();
    private WebView webView;

    private EquatorialWebEngine() { }

    /**
     * Consulta completa pelo motor alternativo: autentica, escolhe o imóvel, emite e lê.
     *
     * @param unit     unidade consumidora esperada (dígitos, como o cofre guarda)
     * @param document CPF ou CNPJ do titular
     * @param deadline instante em que o job desiste; o motor respeita o que sobrou
     */
    static JSONObject read(Context context, String unit, String document, long deadline)
            throws Exception {
        EquatorialWebEngine engine = new EquatorialWebEngine();
        try {
            return engine.run(context.getApplicationContext(), unit, document, deadline);
        } finally {
            engine.destroy();
        }
    }

    /**
     * Entrega do QR do PIX. O base64 nunca passa por log, nem truncado.
     *
     * Callback e nao retorno porque quem chama e a ponte, que roda na thread
     * principal, e este motor precisa dela livre para o WebView responder.
     */
    interface PixSink {
        void onPix(String base64);
        void onFailure(String error);
    }

    /**
     * QR do PIX da fatura pedida, em base64, lido do DOM em vez de da tela.
     *
     * Conferido contra a pagina real: em SegundaViaDownload.aspx cada linha tem um
     * controle com onclick="pix(this,'iVBORw0KGgo...')", e o argumento e o QR ja em
     * PNG. Ler dali dispensa screenshot, resolucao, contraste e adivinhar qual
     * celula e a do PIX pela posicao — as duas incertezas do caminho por imagem.
     *
     * A linha e escolhida pela REFERENCIA pedida, nunca pela posicao, e a escolha e
     * do {@link PixRowLocator}, que ja trata AGO/2026 e 08/2026 como a mesma coisa.
     * Ambiguidade e ausencia falham: entregar o QR da fatura errada custa dinheiro
     * do proprietario.
     *
     * Validacao do payload nao acontece aqui — quem valida e {@link PixPayload},
     * depois de o QR ser decodificado. Este metodo entrega imagem, nao payload.
     */
    static void pixBase64ForReference(Context context, String unit, String document,
                                      String reference, long timeoutMillis, PixSink sink) {
        final Context app = context.getApplicationContext();
        final long deadline = System.currentTimeMillis() + timeoutMillis;
        new Thread(new Runnable() {
            @Override public void run() {
                EquatorialWebEngine engine = new EquatorialWebEngine();
                try {
                    sink.onPix(engine.runPix(app, unit, document, reference, deadline));
                } catch (Exception error) {
                    String message = error.getMessage();
                    sink.onFailure(message == null || message.isEmpty()
                        ? error.getClass().getSimpleName() : message);
                } finally {
                    engine.destroy();
                }
            }
        }, "rod-pix-webview").start();
    }

    private String runPix(Context context, String unit, String document,
                          String reference, long deadline) throws Exception {
        create(context);
        RodLog.step("webview", "motor alternativo iniciado para o QR de pix");
        reachBillPage(unit, document, deadline);
        emitFullInvoice(deadline);
        return pixFromDownloadPage(reference);
    }

    /** Extrai os pares (texto da linha, base64 do QR) e escolhe pela referencia. */
    private String pixFromDownloadPage(String reference) throws Exception {
        String script =
            "(function(){"
            + "var out=[];"
            + "var nodes=document.querySelectorAll('[onclick]');"
            + "for(var i=0;i<nodes.length;i++){"
            + "var oc=nodes[i].getAttribute('onclick')||'';"
            + "if(oc.toLowerCase().indexOf('pix')<0) continue;"
            + "var m=oc.match(/'([A-Za-z0-9+/=]{40,})'/);"
            + "if(!m) continue;"
            + "var row=nodes[i].closest('tr');"
            + "out.push({text:row?row.innerText:'',b64:m[1]});}"
            + "return JSON.stringify({rows:out});"
            + "})()";
        JSONObject dom = new JSONObject(evalJson(script));
        JSONArray rows = dom.optJSONArray("rows");
        int total = rows == null ? 0 : rows.length();
        RodLog.step("webview", "linhas com controle de pix=" + total);
        if (total == 0) throw new IllegalStateException(
            "EQUATORIAL_PAYMENT_DATA_NOT_FOUND: a pagina de download nao expos QR de pix");

        List<String> texts = new ArrayList<>();
        for (int i = 0; i < total; i++) texts.add(rows.getJSONObject(i).optString("text", ""));
        int index = PixRowLocator.invoiceIndex(texts, reference);
        RodLog.step("webview", "linha escolhida pela referencia=" + (index >= 0));
        if (index == PixRowLocator.AMBIGUOUS) throw new IllegalStateException(
            "EQUATORIAL_PAYMENT_DATA_NOT_FOUND: mais de uma fatura casa com a referencia pedida");
        if (index < 0 || index >= total) throw new IllegalStateException(
            "EQUATORIAL_PAYMENT_DATA_NOT_FOUND: nenhuma fatura com a referencia pedida nesta tela");

        String base64 = rows.getJSONObject(index).optString("b64", "");
        // Presenca e tamanho, nunca o conteudo: este e o QR de pagamento do dono.
        RodLog.step("webview", "qr de pix obtido=" + !base64.isEmpty()
            + " tamanho=" + base64.length());
        if (base64.isEmpty()) throw new IllegalStateException(
            "EQUATORIAL_PAYMENT_DATA_NOT_FOUND: controle de pix sem imagem embutida");
        return base64;
    }

    // ------------------------------------------------------------------ fluxo

    private JSONObject run(Context context, String unit, String document, long deadline)
            throws Exception {
        create(context);
        RodLog.step("webview", "motor alternativo iniciado");

        reachBillPage(unit, document, deadline);
        selectUnit(unit, deadline);
        emit(deadline);
        return readBill(unit);
    }

    /**
     * Deixa a segunda via autenticada na frente, autenticando se for preciso.
     *
     * Sessao caida e pagina de erro do portal levam ao mesmo lugar: a tela de
     * acesso. Verificacao humana e credencial recusada param aqui, e param de vez.
     */
    private void reachBillPage(String unit, String document, long deadline) throws Exception {
        load(BILL_URL, deadline);
        Observation seen = observe(false);
        RodLog.step("webview", "estado inicial=" + seen.state);

        if (seen.state == EquatorialSession.State.SESSION_EXPIRED
            || seen.state == EquatorialSession.State.BROWSER_STALE) {
            seen = authenticate(unit, document, deadline);
            RodLog.step("webview", "estado apos autenticar=" + seen.state);
        }
        if (seen.state == EquatorialSession.State.HUMAN_CHECK)
            throw new IllegalStateException(
                "EQUATORIAL_HUMAN_CHECK: a Equatorial pediu verificacao humana no motor WebView");
        if (seen.state == EquatorialSession.State.LOGIN_REJECTED)
            throw new IllegalStateException(
                EquatorialSession.errorFor(EquatorialSession.Decision.FAIL_LOGIN_REJECTED));
        if (seen.state != EquatorialSession.State.SESSION_VALID
            && seen.state != EquatorialSession.State.LOGIN_OK)
            throw new IllegalStateException(
                EquatorialSession.errorFor(EquatorialSession.Decision.FAIL_EXHAUSTED));

        if (!seen.billSelector) {
            load(BILL_URL, deadline);
            seen = observe(false);
            if (!seen.billSelector) throw new IllegalStateException(
                "EQUATORIAL_BILL_NOT_FOUND: o motor WebView nao carregou o seletor de unidade");
        }
    }

    /**
     * Autentica no portal por DOM.
     *
     * Escrever num campo dispara JS que limpa o outro: o mesmo comportamento que
     * obrigou o motor de acessibilidade a conferir e reaplicar. Aqui a conferência
     * é imediata, porque ler o value de volta custa uma chamada.
     */
    private Observation authenticate(String unit, String document, long deadline) throws Exception {
        // Cookie velho é a causa mais comum de o portal insistir na tela de login.
        // Neste motor, apagá-lo é seguro.
        dropOwnSessionInline();
        load(LOGIN_URL, deadline);

        String script =
            "(function(){"
            + "var u=document.getElementById('WEBDOOR_headercorporativogo_txtUC');"
            + "var d=document.getElementById('WEBDOOR_headercorporativogo_txtDocumento');"
            + "if(!u||!d) return JSON.stringify({fields:false});"
            + "function put(el,v){el.focus();el.value=v;"
            + "el.dispatchEvent(new Event('input',{bubbles:true}));"
            + "el.dispatchEvent(new Event('change',{bubbles:true}));}"
            + "put(u," + JSONObject.quote(unit) + ");"
            + "put(d," + JSONObject.quote(document) + ");"
            + "put(u," + JSONObject.quote(unit) + ");"
            + "return JSON.stringify({fields:true,unit:u.value.length>0,doc:d.value.length>0});"
            + "})()";
        JSONObject filled = new JSONObject(evalJson(script));
        RodLog.step("webview", "campos de login presentes=" + filled.optBoolean("fields", false)
            + " unidade=" + filled.optBoolean("unit", false)
            + " documento=" + filled.optBoolean("doc", false));
        if (!filled.optBoolean("unit", false) || !filled.optBoolean("doc", false))
            throw new IllegalStateException(
                "EQUATORIAL_PORTAL_TIMEOUT: o motor WebView nao encontrou a tela de autenticacao");

        // Só o botão que uma pessoa consegue tocar. O <input> de postback do
        // ASP.NET existe escondido na página, e aciona-lo direto pularia o token
        // de risco que o portal exige — isso seria contornar um controle de
        // seguranca, e nao e o que este motor faz.
        String submit =
            "(function(){"
            + "var b=Array.prototype.slice.call(document.querySelectorAll("
            + "'button,input[type=submit],input[type=button],a')).filter(function(e){"
            + "var t=((e.value||'')+' '+(e.textContent||'')).trim().toLowerCase();"
            + "return t==='entrar'&&!!e.offsetParent;});"
            + "var risk=(typeof window.tsPlatform!=='undefined');"
            + "if(!b.length) return JSON.stringify({clicked:false,risk:risk});"
            + "b[0].click();"
            + "return JSON.stringify({clicked:true,risk:risk});"
            + "})()";
        JSONObject sent = new JSONObject(evalJson(submit));
        boolean clicked = sent.optBoolean("clicked", false);
        // O portal gera um token de risco pelo SDK dele antes de enviar o
        // formulario. Se esse SDK nao carregou no WebView, o login nao acontece —
        // e saber disso pela trilha evita procurar o defeito no lugar errado.
        RodLog.step("webview", "ENTRAR acionado=" + clicked
            + " sdk de risco do portal presente=" + sent.optBoolean("risk", false));
        if (!clicked) throw new IllegalStateException(
            "EQUATORIAL_PORTAL_TIMEOUT: botao ENTRAR ausente no motor WebView");

        // Agir devolve sucesso sem a página ter reagido, aqui como no Chrome: o que
        // vale é a próxima observação. E o veredito demora, porque o portal só faz
        // o postback depois de o token existir — observar uma vez e concluir dava
        // login falhado um instante antes de ele dar certo.
        return awaitLoginOutcome(Math.min(deadline, System.currentTimeMillis() + LOGIN_WAIT_MILLIS));
    }

    /** Observa até o portal decidir, ou até o prazo. Estado, nunca tempo fixo. */
    private Observation awaitLoginOutcome(long limit) throws Exception {
        Observation seen = observe(true);
        while (seen.state == EquatorialSession.State.LOGIN_IN_PROGRESS
            && System.currentTimeMillis() < limit) {
            Thread.sleep(POLL_MILLIS * 2);
            seen = observe(true);
        }
        return seen;
    }

    /** Escolhe a unidade no combo da segunda via, casando dígitos como o outro motor. */
    private void selectUnit(String unit, long deadline) throws Exception {
        String script =
            "(function(){"
            + "var s=document.getElementById('CONTENT_comboBoxUC');"
            + "if(!s) return JSON.stringify({found:false,options:0});"
            + "function norm(v){v=(v||'').replace(/\\D/g,'');return v.replace(/^0+(?!$)/,'');}"
            + "var want=norm(" + JSONObject.quote(unit) + ");"
            + "for(var i=0;i<s.options.length;i++){"
            + "if(norm(s.options[i].text)===want||norm(s.options[i].value)===want){"
            + "s.selectedIndex=i;s.dispatchEvent(new Event('change',{bubbles:true}));"
            + "return JSON.stringify({found:true,options:s.options.length});}}"
            + "return JSON.stringify({found:false,options:s.options.length});"
            + "})()";
        JSONObject picked = new JSONObject(evalJson(script));
        RodLog.step("webview", "unidades no combo=" + picked.optInt("options", -1)
            + " imovel escolhido=" + picked.optBoolean("found", false));
        if (!picked.optBoolean("found", false))
            throw new IllegalStateException(picked.optInt("options", 0) > 0
                ? "EQUATORIAL_PROPERTY_NOT_MAPPED: a unidade configurada nao esta entre as "
                    + picked.optInt("options", 0) + " deste login"
                : "EQUATORIAL_CONTRACT_NOT_FOUND: a lista de unidades veio vazia");
        settle(deadline);
    }

    /**
     * Preenche tipo e motivo e emite.
     *
     * "Apenas código de barras" renderiza o dado na própria página; "fatura
     * completa" baixa um PDF, que este motor não sabe ler. O motivo é "Outros",
     * pelo mesmo critério do outro motor: é a única opção que não afirma algo
     * falso em nome do proprietário.
     */
    private void emit(long deadline) throws Exception {
        emit(deadline, new String[]{"codigo de barras", "código de barras"});
    }

    /**
     * "Fatura completa" leva a SegundaViaDownload.aspx, que e onde vive o QR do PIX.
     *
     * A leitura normal nao usa esta rota porque ela produz PDF, e PDF nao se le
     * pela arvore. Para o PIX ela e obrigatoria: o base64 do QR esta no onclick do
     * controle da linha, no DOM daquela pagina.
     */
    private void emitFullInvoice(long deadline) throws Exception {
        emit(deadline, new String[]{"fatura completa", "completa"});
    }

    /** Emite o tipo pedido; as palavras viajam para o JS como literais JSON. */
    private void emit(long deadline, String[] typeWords) throws Exception {
        StringBuilder words = new StringBuilder();
        for (String word : typeWords) {
            if (words.length() > 0) words.append(',');
            words.append(JSONObject.quote(word.toLowerCase()));
        }
        String script =
            "(function(){"
            + "function pick(id,words){var s=document.getElementById(id);"
            + "if(!s) return false;"
            + "for(var i=0;i<s.options.length;i++){"
            + "var t=(s.options[i].text||'').toLowerCase();"
            + "for(var w=0;w<words.length;w++) if(t.indexOf(words[w])>=0){"
            + "s.selectedIndex=i;s.dispatchEvent(new Event('change',{bubbles:true}));return true;}}"
            + "return false;}"
            + "var tipo=pick('CONTENT_cbTipoEmissao',[" + words + "]);"
            + "var motivo=pick('CONTENT_cbMotivo',['outros']);"
            + "var b=document.getElementById('CONTENT_btEnviar');"
            + "if(b) b.click();"
            + "return JSON.stringify({tipo:tipo,motivo:motivo,enviado:!!b});"
            + "})()";
        JSONObject form = new JSONObject(evalJson(script));
        RodLog.step("webview", "tipo=" + form.optBoolean("tipo", false)
            + " motivo=" + form.optBoolean("motivo", false)
            + " emitir=" + form.optBoolean("enviado", false));
        if (!form.optBoolean("enviado", false))
            throw new IllegalStateException(
                "EQUATORIAL_BILL_NOT_FOUND: botao Emitir ausente no motor WebView");
        settle(deadline);
    }

    /** Lê a fatura do DOM e delega a extração ao parser, que é o mesmo dos dois motores. */
    private JSONObject readBill(String expectedUnit) throws Exception {
        String text = evalJson("document.body?document.body.innerText:''");
        EquatorialTextParser.Page page = EquatorialTextParser.parse(text);
        if (page.state == EquatorialTextParser.State.AUTH_REQUIRED)
            throw new IllegalStateException(
                EquatorialSession.errorFor(EquatorialSession.Decision.FAIL_EXHAUSTED));
        if (page.state == EquatorialTextParser.State.HUMAN_CHECK)
            throw new IllegalStateException(
                "EQUATORIAL_HUMAN_CHECK: a Equatorial pediu verificacao humana no motor WebView");
        if (page.state == EquatorialTextParser.State.NO_BILL)
            throw new IllegalStateException(
                "EQUATORIAL_BILL_NOT_FOUND: nenhuma fatura visivel no motor WebView");

        String shown = page.get("uc").replaceAll("\\D", "");
        String expected = expectedUnit == null ? "" : expectedUnit.replaceAll("\\D", "");
        if (!shown.isEmpty() && !expected.isEmpty()
            && !EquatorialSession.sameUnit(shown, expected)) {
            RodLog.fail("webview", "a pagina mostra outro imovel");
            throw new IllegalStateException(
                "EQUATORIAL_CONTRACT_NOT_FOUND: a tela mostra outra unidade consumidora");
        }
        RodLog.found("webview", "valor", !page.get("amount").isEmpty());
        RodLog.found("webview", "vencimento", !page.get("due_date").isEmpty());
        RodLog.found("webview", "referencia", !page.get("reference").isEmpty());
        RodLog.found("webview", "codigo de barras", !page.get("barcode").isEmpty());
        RodLog.found("webview", "pix", !page.get("pix").isEmpty());
        return new JSONObject()
            .put("source", "equatorial_rod_webview")
            .put("amount", page.get("amount"))
            .put("due_date", page.get("due_date"))
            .put("reference", page.get("reference"))
            .put("barcode", page.get("barcode"))
            .put("pix", page.get("pix"));
    }

    // --------------------------------------------------------------- observação

    private static final class Observation {
        final EquatorialSession.State state;
        final boolean billSelector;
        Observation(EquatorialSession.State state, boolean billSelector) {
            this.state = state;
            this.billSelector = billSelector;
        }
    }

    /**
     * Uma olhada no DOM traduzida no vocabulário da máquina de sessão.
     *
     * A presença dos elementos é estrutural — getElementById, não texto — porque
     * o rodapé do portal fala de login em toda página, inclusive nas autenticadas.
     */
    private Observation observe(boolean afterSubmit) throws Exception {
        String script =
            "(function(){"
            + "var bill=!!document.getElementById('CONTENT_comboBoxUC');"
            + "var login=!!(document.getElementById('WEBDOOR_headercorporativogo_txtUC')"
            + "&&document.getElementById('WEBDOOR_headercorporativogo_txtDocumento'));"
            + "var t=document.body?document.body.innerText:'';"
            + "return JSON.stringify({bill:bill,login:login,text:t});"
            + "})()";
        JSONObject dom;
        try {
            dom = new JSONObject(evalJson(script));
        } catch (Exception error) {
            return new Observation(EquatorialSession.State.BROWSER_STALE, false);
        }
        boolean bill = dom.optBoolean("bill", false);
        boolean login = dom.optBoolean("login", false);
        String text = dom.optString("text", "");
        boolean responding = !failed.get() && (bill || login || !text.trim().isEmpty());
        EquatorialSession.State state =
            EquatorialSession.classify(text, responding, bill, login, afterSubmit);
        return new Observation(state, bill);
    }

    // ------------------------------------------------------------------ WebView

    private void create(final Context context) throws Exception {
        final ArrayBlockingQueue<Object> ready = new ArrayBlockingQueue<>(1);
        main.post(new Runnable() {
            @Override public void run() {
                try {
                    CookieManager.getInstance().setAcceptCookie(true);
                    WebView view = new WebView(context);
                    WebSettings settings = view.getSettings();
                    settings.setJavaScriptEnabled(true);
                    settings.setDomStorageEnabled(true);
                    settings.setDatabaseEnabled(true);
                    settings.setLoadsImagesAutomatically(false);
                    settings.setBlockNetworkImage(true);
                    view.setWebViewClient(new WebViewClient() {
                        @Override public void onPageFinished(WebView source, String url) {
                            loads.incrementAndGet();
                        }
                        @Override public void onReceivedError(WebView source, WebResourceRequest request,
                                                             WebResourceError error) {
                            // Só o documento principal importa; recurso secundário
                            // falhando não invalida a página.
                            if (request != null && request.isForMainFrame()) {
                                failed.set(true);
                                RodLog.fail("webview", "erro de rede no documento principal");
                            }
                        }
                    });
                    // Sem janela, nada é medido: sem medir, o layout não existe e
                    // scripts que dependem de dimensão não rodam.
                    view.measure(
                        View.MeasureSpec.makeMeasureSpec(VIEWPORT_WIDTH, View.MeasureSpec.EXACTLY),
                        View.MeasureSpec.makeMeasureSpec(VIEWPORT_HEIGHT, View.MeasureSpec.EXACTLY));
                    view.layout(0, 0, VIEWPORT_WIDTH, VIEWPORT_HEIGHT);
                    webView = view;
                    ready.offer(Boolean.TRUE);
                } catch (Throwable error) {
                    ready.offer(error);
                }
            }
        });
        Object outcome = ready.poll(EVAL_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS);
        if (outcome instanceof Throwable)
            throw new IllegalStateException("EQUATORIAL_WEBVIEW_UNAVAILABLE: "
                + ((Throwable) outcome).getClass().getSimpleName());
        if (outcome == null)
            throw new IllegalStateException("EQUATORIAL_WEBVIEW_UNAVAILABLE: motor nao iniciou");
    }

    private void destroy() {
        main.post(new Runnable() {
            @Override public void run() {
                if (webView != null) {
                    webView.stopLoading();
                    webView.destroy();
                    webView = null;
                }
            }
        });
    }

    private void dropOwnSessionInline() {
        main.post(new Runnable() {
            @Override public void run() {
                CookieManager cookies = CookieManager.getInstance();
                cookies.removeSessionCookies(null);
                cookies.flush();
                if (webView != null) webView.clearCache(true);
            }
        });
    }

    /**
     * Navega e espera a PAGINA NOVA, nao qualquer pagina completa.
     *
     * Esperar apenas por readyState "complete" devolvia na hora: o documento
     * anterior ja estava completo antes de a navegacao nova nem comecar, e a
     * observacao seguinte classificava a pagina errada. Contar os fins de
     * carregamento resolve, porque um deles so acontece depois da troca.
     */
    private void load(final String url, long deadline) throws Exception {
        failed.set(false);
        int before = loads.get();
        main.post(new Runnable() {
            @Override public void run() { if (webView != null) webView.loadUrl(url); }
        });
        settle(deadline, before);
    }

    /** Espera a página assentar. Estado observável, nunca tempo fixo. */
    private void settle(long deadline) throws Exception {
        settle(deadline, loads.get() - 1);
    }

    private void settle(long deadline, int loadsBefore) throws Exception {
        long limit = Math.min(deadline, System.currentTimeMillis() + LOAD_TIMEOUT_MILLIS);
        while (System.currentTimeMillis() < limit) {
            Thread.sleep(POLL_MILLIS);
            if (failed.get()) return;
            if (loads.get() <= loadsBefore) continue;
            String state;
            try {
                state = evalJson("document.readyState");
            } catch (Exception ignored) {
                continue;
            }
            if ("complete".equals(state)) return;
        }
    }

    /**
     * Avalia JS e devolve a string que o script serializou.
     *
     * evaluateJavascript entrega JSON, então uma string vem entre aspas e com
     * escapes. Desembrulhar aqui evita que cada chamador repita esse cuidado — e
     * um deles esquecia, o que fazia o parser receber a página com \n literais.
     */
    private String evalJson(final String script) throws Exception {
        final ArrayBlockingQueue<String> answer = new ArrayBlockingQueue<>(1);
        main.post(new Runnable() {
            @Override public void run() {
                if (webView == null) { answer.offer("null"); return; }
                webView.evaluateJavascript(script, value -> answer.offer(value == null ? "null" : value));
            }
        });
        String raw = answer.poll(EVAL_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS);
        if (raw == null)
            throw new IllegalStateException("EQUATORIAL_PORTAL_TIMEOUT: motor WebView nao respondeu");
        return unwrap(raw);
    }

    /** Desembrulha o valor JSON devolvido por evaluateJavascript. */
    static String unwrap(String raw) throws Exception {
        if (raw == null || raw.equals("null")) return "";
        return new JSONObject("{\"v\":" + raw + "}").optString("v", "");
    }
}
