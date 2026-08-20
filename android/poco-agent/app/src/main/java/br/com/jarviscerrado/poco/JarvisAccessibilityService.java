package br.com.jarviscerrado.poco;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.Uri;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.graphics.Path;
import android.graphics.Rect;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import org.json.JSONObject;

public class JarvisAccessibilityService extends AccessibilityService {
    static final String ACTION_BRIDGE = "br.com.jarviscerrado.poco.ACCESSIBILITY_BRIDGE";
    static final String PREFS_BRIDGE = "accessibility_bridge";
    private static final String SANEAGO = "br.com.saneago";
    private static final String CHROME = "com.android.chrome";
    /** Prazo total para a pagina da Equatorial assentar num estado legivel. */
    private static final long PAGE_SETTLE_MILLIS = 25_000L;
    /** Intervalo entre releituras da arvore enquanto a pagina carrega. */
    private static final long PAGE_POLL_MILLIS = 600L;
    /** Prazo para a home autenticada renderizar o seletor de imovel. */
    private static final long CHOOSER_RENDER_MILLIS = 12_000L;
    /** Prazo para a lista nativa de contratos aparecer depois do toque. */
    private static final long DIALOG_OPEN_MILLIS = 5_000L;
    /** Prazo para a lista nativa sair da frente depois da escolha. */
    private static final long DIALOG_CLOSE_MILLIS = 6_000L;
    /** Intervalo entre releituras da arvore nas transicoes curtas. */
    private static final long UI_POLL_MILLIS = 400L;
    /** Toques no seletor de imovel antes de desistir. */
    private static final int CONTRACT_OPEN_ATTEMPTS = 3;
    /** BACKs no dialogo nativo antes de desistir de fecha-lo. */
    private static final int CONTRACT_CLOSE_ATTEMPTS = 3;
    /**
     * Ids do dialogo nativo com que o Chrome desenha um &lt;select&gt;.
     *
     * A lista de contratos do portal nao e conteudo web: e uma janela do sistema,
     * e enquanto ela esta na frente packageRoot(CHROME) devolve null.
     */
    private static final String[] DIALOG_VIEW_IDS = {
        "id/parentPanel", "id/customPanel", "id/select_dialog_listview", "id/text1"
    };

    private final BroadcastReceiver bridge = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            String request = intent.getStringExtra("request_id");
            String operation = intent.getStringExtra("operation");
            if (request == null || operation == null) return;
            RodLog.step("ponte", "operacao=" + operation);
            try {
                if (operation.equals("open_saneago")) {
                    bringSaneagoToFront(request);
                } else if (operation.equals("read_saneago")) {
                    if (Build.VERSION.SDK_INT >= 31) performGlobalAction(GLOBAL_ACTION_DISMISS_NOTIFICATION_SHADE);
                    new Handler(Looper.getMainLooper()).postDelayed(() -> readSaneagoWithFallback(request), 1800);
                } else if (operation.equals("login_saneago")) {
                    loginSaneago(request, intent.getStringExtra("login"), intent.getStringExtra("password"), 0);
                } else if (operation.equals("select_saneago")) {
                    selectSaneago(request, intent.getStringExtra("account"), 0);
                } else if (operation.equals("open_equatorial")) {
                    openEquatorial(request, 0);
                } else if (operation.equals("dismiss_equatorial")) {
                    dismissEquatorialOverlay(request);
                } else if (operation.equals("select_equatorial")) {
                    selectEquatorialContract(request, intent.getStringExtra("unit"), 0);
                } else if (operation.equals("read_equatorial")) {
                    readEquatorial(request, intent.getStringExtra("unit"));
                } else reply(request, false, null, "Operacao nao permitida");
            } catch (Exception error) {
                reply(request, false, null, error.getClass().getSimpleName() + ": " + error.getMessage());
            }
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        IntentFilter filter = new IntentFilter(ACTION_BRIDGE);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(bridge, filter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(bridge, filter);
    }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }
    @Override public void onInterrupt() { }
    @Override public void onDestroy() { unregisterReceiver(bridge); super.onDestroy(); }

    private void bringSaneagoToFront(String request) {
        performGlobalAction(GLOBAL_ACTION_HOME);
        startActivity(new Intent(this, WakeActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            try {
                Intent launch = getPackageManager().getLaunchIntentForPackage(SANEAGO);
                if (launch == null) throw new IllegalStateException("Saneago nao instalado");
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                startActivity(launch);
                reply(request, true, new JSONObject().put("opened", true), null);
            } catch (Exception error) {
                reply(request, false, null, error.getClass().getSimpleName() + ": " + error.getMessage());
            }
        }, 1500);
    }

    private void loginSaneago(String request, String login, String password, int attempt) {
        if (login == null || password == null || login.isEmpty() || password.isEmpty()) {
            reply(request, false, null, "Credenciais Saneago ausentes no cofre");
            return;
        }
        AccessibilityNodeInfo root = saneagoRoot();
        if (root == null) root = packageRoot(CHROME);
        if (root == null) { reply(request, false, null, "Tela de login Saneago nao encontrada"); return; }
        List<AccessibilityNodeInfo> editors = new ArrayList<>();
        collectEditors(root, editors);
        if (editors.size() < 2) {
            boolean opened = gestureClickLabel(root, "faca login", "faça login", "abrir tela de login");
            root.recycle();
            if (attempt < 3) {
                if (!opened) {
                    Intent loginIntent = new Intent(Intent.ACTION_VIEW, Uri.parse("br.com.saneago://login"))
                        .setPackage(SANEAGO).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    startActivity(loginIntent);
                }
                new Handler(Looper.getMainLooper()).postDelayed(
                    () -> loginSaneago(request, login, password, attempt + 1), 2200
                );
                return;
            }
            reply(request, false, null, "Campos de login Saneago nao estao acessiveis nesta tela");
            return;
        }
        setNodeText(editors.get(0), login);
        setNodeText(editors.get(1), password);
        boolean clicked = gestureClickLabel(root, "entrar", "acessar");
        if (!clicked) clicked = clickFirst(root, "entrar", "acessar", "login");
        for (AccessibilityNodeInfo editor : editors) editor.recycle();
        root.recycle();
        reply(request, clicked, new JSONObject(), clicked ? null : "Botao de entrada Saneago nao encontrado");
    }

    private void selectSaneago(String request, String account, int step) {
        String expected = digits(account);
        if (expected.isEmpty()) { reply(request, false, null, "Conta Saneago ausente"); return; }
        AccessibilityNodeInfo root = saneagoRoot();
        if (root == null) { reply(request, false, null, "Tela Saneago nao encontrada"); return; }
        if (containsDigits(root, expected)) {
            boolean current = step == 0 && containsLabel(root, "fatura atual");
            if (current) {
                root.recycle();
                reply(request, true, new JSONObject(), null);
                return;
            }
            boolean clicked = gestureClickDigits(root, expected);
            root.recycle();
            if (clicked) {
                new Handler(Looper.getMainLooper()).postDelayed(
                    () -> confirmSaneagoSelection(request), 900);
            } else {
                reply(request, false, null, "Conta Saneago encontrada, mas nao selecionavel");
            }
            return;
        }
        boolean advanced = false;
        boolean returnHome = false;
        if (step == 0) {
            advanced = gestureClickLabel(root, "conta:");
            if (!advanced && containsLabel(root, "agência virtual")) {
                returnHome = gestureClickLabel(root, "home");
            }
        }
        else if (step == 1) advanced = gestureClickLabel(root, "trocar conta", "minhas contas", "contas");
        root.recycle();
        if (returnHome) {
            new Handler(Looper.getMainLooper()).postDelayed(
                () -> selectSaneago(request, account, 0), 1800
            );
            return;
        }
        if (advanced && step < 2) {
            new Handler(Looper.getMainLooper()).postDelayed(
                () -> selectSaneago(request, account, step + 1), 1800
            );
            return;
        }
        reply(request, false, null, "Conta Saneago nao apareceu no seletor");
    }

    private void confirmSaneagoSelection(String request) {
        AccessibilityNodeInfo root = saneagoRoot();
        if (root == null) { reply(request, false, null, "Confirmacao da conta Saneago nao encontrada"); return; }
        boolean clicked = gestureClickLabel(root, "ok", "confirmar");
        root.recycle();
        if (clicked) {
            new Handler(Looper.getMainLooper()).postDelayed(
                () -> reply(request, true, new JSONObject(), null), 1800);
        } else {
            reply(request, false, null, "Botao OK da conta Saneago nao encontrado");
        }
    }

    /**
     * Fecha o aviso de privacidade e confirma que ele saiu.
     *
     * Fechar e clicar no mesmo passo nao funcionava: o clique em "Acessar" era
     * reportado como sucesso mas o modal ainda cobria a pagina, entao nada
     * avancava. O fechamento agora e um passo proprio, com verificacao.
     */
    private void dismissEquatorialOverlay(String request) {
        AccessibilityNodeInfo root = packageRoot(CHROME);
        if (root == null) { reply(request, false, null, "Portal Equatorial nao encontrado no Chrome"); return; }
        if (!hasOverlay(root)) {
            RodLog.step("aviso", "nao havia aviso sobreposto");
            root.recycle(); reply(request, true, new JSONObject(), null); return;
        }
        RodLog.step("aviso", "aviso presente, tentando fechar");
        // Gesto primeiro. Em conteudo web, ACTION_CLICK devolve true mesmo quando a
        // pagina nao reage, o que escondia a falha e impedia a segunda tentativa.
        // E o mesmo motivo pelo qual o login da Saneago ja tenta o gesto antes.
        if (!gestureClickLabel(root, "fechar")) clickFirst(root, "fechar");
        root.recycle();
        new Handler(Looper.getMainLooper()).postDelayed(() -> retireOverlay(request, 0), 1500);
    }

    private void retireOverlay(String request, int attempt) {
        AccessibilityNodeInfo root = packageRoot(CHROME);
        if (root == null) { reply(request, false, null, "Portal Equatorial nao encontrado no Chrome"); return; }
        if (!hasOverlay(root)) {
            RodLog.step("aviso", "fechado na tentativa " + attempt);
            root.recycle(); reply(request, true, new JSONObject(), null); return;
        }
        RodLog.step("aviso", "ainda presente na tentativa " + attempt);
        if (attempt >= 2) {
            root.recycle();
            reply(request, false, null,
                "EQUATORIAL_PORTAL_TIMEOUT: o aviso de privacidade do portal nao fechou");
            return;
        }
        if (attempt == 0) {
            if (!gestureClickLabel(root, "fechar")) clickFirst(root, "fechar");
        } else if (systemDialogInFront()) {
            // BACK so e seguro contra dialogo do sistema. Em conteudo web ele navega
            // o Chrome para tras: na volta hasOverlay e falso e o passo respondia
            // sucesso estando em OUTRA pagina, sem aviso nenhum.
            RodLog.step("aviso", "aviso e dialogo do sistema, fechando com voltar");
            performGlobalAction(GLOBAL_ACTION_BACK);
        } else {
            RodLog.step("aviso", "aviso e conteudo web, repetindo o toque em fechar");
            if (!gestureClickLabel(root, "fechar", "close")) clickFirst(root, "fechar");
        }
        root.recycle();
        new Handler(Looper.getMainLooper()).postDelayed(() -> retireOverlay(request, attempt + 1), 1500);
    }

    private static boolean hasOverlay(AccessibilityNodeInfo root) {
        return containsLabel(root, "aviso de privacidade") || containsLabel(root, "seus direitos garantidos");
    }


    /**
     * Agencia Virtual da Equatorial: unidade consumidora e CPF.
     *
     * A home so pede o CPF e leva para esta tela. Aqui os campos tem
     * resource-id estavel, entao nao dependemos da ordem em que aparecem.
     */
    /**
     * Abre o portal e confirma que o Chrome realmente ficou visivel.
     *
     * O passo antigo disparava o Intent e respondia "ok" em poucos milissegundos,
     * sem verificar nada. Com a tela apagada o Chrome nao chegava a aparecer para
     * o servico de acessibilidade e o passo seguinte falhava sem explicacao.
     *
     * O SCREEN_BRIGHT_WAKE_LOCK usado pelo leitor esta depreciado desde a API 17 e
     * nao acende mais a tela no Android 12; por isso a WakeActivity, que ja servia
     * ao fluxo da Saneago, passa a valer tambem aqui.
     */
    private void openEquatorial(String request, int attempt) {
        if (attempt == 0) {
            RodLog.step("abertura", "acordando a tela antes de abrir o portal");
            performGlobalAction(GLOBAL_ACTION_HOME);
            startActivity(new Intent(this, WakeActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            new Handler(Looper.getMainLooper()).postDelayed(() -> openEquatorial(request, 1), 1600);
            return;
        }
        if (attempt == 1) {
            RodLog.step("abertura", "abrindo o portal no Chrome");
            Intent browser = new Intent(Intent.ACTION_VIEW, Uri.parse("https://go.equatorialenergia.com.br/"));
            browser.setPackage(CHROME)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            startActivity(browser);
            new Handler(Looper.getMainLooper()).postDelayed(() -> openEquatorial(request, 2), 3000);
            return;
        }
        AccessibilityNodeInfo root = packageRoot(CHROME);
        if (root != null) {
            root.recycle();
            RodLog.step("abertura", "Chrome visivel na tentativa " + attempt);
            reply(request, true, new JSONObject(), null);
            return;
        }
        if (attempt >= 6) {
            RodLog.fail("abertura", "Chrome nao ficou visivel");
            reply(request, false, null, "O Chrome nao abriu o portal da Equatorial");
            return;
        }
        RodLog.step("abertura", "Chrome ainda nao visivel, aguardando (tentativa " + attempt + ")");
        new Handler(Looper.getMainLooper()).postDelayed(() -> openEquatorial(request, attempt + 1), 1500);
    }

    private static AccessibilityNodeInfo findByViewId(AccessibilityNodeInfo node, String suffix) {
        String viewId = node.getViewIdResourceName();
        if (viewId != null && viewId.endsWith(suffix)) return AccessibilityNodeInfo.obtain(node);
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                AccessibilityNodeInfo found = findByViewId(child, suffix);
                child.recycle();
                if (found != null) return found;
            }
        }
        return null;
    }

    /**
     * Abre o seletor de imovel da area autenticada.
     *
     * A home autenticada mostra "Selecione Unidade Consumidora" com o contrato
     * corrente. O portal identifica cada imovel por conta contrato, que e um
     * numero diferente da unidade consumidora guardada no cofre, entao a
     * correspondencia e tentada pelos dois: primeiro pelos digitos configurados,
     * e so entao abrindo a lista para inspecao.
     */
    private void selectEquatorialContract(String request, String expectedUnit, int attempt) {
        awaitContractChooser(request, ContractMatch.normalize(expectedUnit),
            System.currentTimeMillis() + CHOOSER_RENDER_MILLIS);
    }

    /**
     * Espera a home autenticada renderizar antes de decidir qualquer coisa.
     *
     * A ausencia do rotulo do seletor valia como "ja estamos fora da home" e o
     * passo respondia sucesso. Pagina lenta virava selecao pulada em silencio, e
     * a consulta seguinte lia a fatura do imovel da consulta anterior. Agora a
     * ausencia so vale quando a propria pagina confirma a unidade pedida; fora
     * isso, espera-se ate o prazo e falha-se com codigo.
     */
    private void awaitContractChooser(String request, String expected, long deadline) {
        AccessibilityNodeInfo leftover = contractDialogRoot();
        if (leftover != null) {
            // Lista nativa que sobrou de uma consulta anterior: enquanto ela estiver
            // na frente a raiz do Chrome nem existe.
            leftover.recycle();
            RodLog.step("contrato", "lista nativa residual na frente, fechando");
            performGlobalAction(GLOBAL_ACTION_BACK);
            if (System.currentTimeMillis() < deadline) { pollContractChooser(request, expected, deadline); return; }
            reply(request, false, null,
                "EQUATORIAL_PORTAL_TIMEOUT: a lista de contratos ficou aberta de uma consulta anterior");
            return;
        }
        AccessibilityNodeInfo root = packageRoot(CHROME);
        if (root == null) {
            if (System.currentTimeMillis() < deadline) { pollContractChooser(request, expected, deadline); return; }
            reply(request, false, null,
                "EQUATORIAL_PORTAL_TIMEOUT: o portal nao ficou visivel no Chrome");
            return;
        }
        if (containsLabel(root, "selecione unidade consumidora")) {
            root.recycle();
            RodLog.step("contrato", "seletor de imovel presente");
            openContractSelector(request, expected, 0);
            return;
        }
        List<String> values = new ArrayList<>();
        collect(root, values);
        root.recycle();
        EquatorialTextParser.Page page = EquatorialTextParser.parse(String.join("\n", values));
        if (page.state == EquatorialTextParser.State.AUTH_REQUIRED) {
            RodLog.fail("contrato", "portal devolveu a tela de autenticacao");
            reply(request, false, null, "EQUATORIAL_AUTH_REQUIRED: a sessao da Equatorial expirou no Poco");
            return;
        }
        if (page.state == EquatorialTextParser.State.HUMAN_CHECK) {
            RodLog.fail("contrato", "portal exibiu desafio de verificacao humana");
            reply(request, false, null, "EQUATORIAL_HUMAN_CHECK: a Equatorial pediu verificacao humana");
            return;
        }
        String shown = ContractMatch.normalize(page.get("uc"));
        if (!expected.isEmpty() && shown.equals(expected)) {
            RodLog.step("contrato", "a tela ja confirma o imovel pedido");
            reply(request, true, new JSONObject(), null);
            return;
        }
        if (System.currentTimeMillis() < deadline) { pollContractChooser(request, expected, deadline); return; }
        RodLog.fail("contrato", "seletor de imovel nao apareceu na home");
        reply(request, false, null,
            "EQUATORIAL_PORTAL_TIMEOUT: o seletor de imovel nao apareceu na home do portal");
    }

    private void pollContractChooser(String request, String expected, long deadline) {
        new Handler(Looper.getMainLooper()).postDelayed(
            () -> awaitContractChooser(request, expected, deadline), UI_POLL_MILLIS);
    }

    /**
     * Toca no seletor de imovel; quem confirma a abertura e a arvore, nao o gesto.
     *
     * dispatchGesture devolve true por ter despachado o toque, e nao por a tela ter
     * reagido. O ramo de nova tentativa era inalcancavel — o metodo nunca recursava
     * — entao "nao abriu" seguia adiante e virava sucesso.
     */
    private void openContractSelector(String request, String expected, int attempt) {
        AccessibilityNodeInfo root = packageRoot(CHROME);
        if (root == null) {
            reply(request, false, null,
                "EQUATORIAL_PORTAL_TIMEOUT: o portal saiu da frente ao abrir o seletor de imovel");
            return;
        }
        Rect window = new Rect();
        root.getBoundsInScreen(window);
        boolean touched = !expected.isEmpty() && gestureClickContractDigits(root, expected, window);
        if (!touched) {
            AccessibilityNodeInfo selector = findByViewId(root, "conta_contrato");
            if (selector == null) selector = findByViewId(root, "select-contract");
            touched = selector != null && gestureClickNode(selector);
            if (selector != null) selector.recycle();
        }
        if (!touched) touched = gestureClickLabel(root, "selecione unidade consumidora");
        root.recycle();
        RodLog.step("contrato", "toque no seletor despachado=" + touched + " tentativa=" + attempt);
        awaitContractDialog(request, expected, attempt, System.currentTimeMillis() + DIALOG_OPEN_MILLIS);
    }

    /** A lista abriu de fato? Se nao, o toque se repete de verdade ate o limite. */
    private void awaitContractDialog(String request, String expected, int attempt, long deadline) {
        AccessibilityNodeInfo dialog = contractDialogRoot();
        if (dialog != null) {
            dialog.recycle();
            RodLog.step("contrato", "lista de contratos aberta");
            resolveContractDialog(request, expected);
            return;
        }
        if (System.currentTimeMillis() < deadline) {
            new Handler(Looper.getMainLooper()).postDelayed(
                () -> awaitContractDialog(request, expected, attempt, deadline), UI_POLL_MILLIS);
            return;
        }
        if (attempt + 1 < CONTRACT_OPEN_ATTEMPTS) {
            RodLog.step("contrato", "lista nao abriu, repetindo o toque na tentativa " + (attempt + 1));
            openContractSelector(request, expected, attempt + 1);
            return;
        }
        RodLog.fail("contrato", "lista de contratos nao abriu");
        reply(request, false, null,
            "EQUATORIAL_PORTAL_TIMEOUT: o seletor de imovel nao abriu a lista de contratos");
    }

    /**
     * Resolve a lista de contratos, que o Chrome desenha como dialogo do sistema.
     *
     * O <select> do portal nao vira conteudo web: vira um dialogo nativo, fora da
     * janela do Chrome, e enquanto ele estiver na frente a raiz do Chrome some.
     * Deixa-lo aberto derrubava tambem a consulta seguinte. Por isso todo caminho
     * daqui, inclusive os de erro, termina com a lista comprovadamente fora da
     * frente — e o sucesso so e reportado depois de reobservar esse fechamento.
     */
    private void resolveContractDialog(String request, String expected) {
        AccessibilityNodeInfo dialog = contractDialogRoot();
        if (dialog == null) {
            RodLog.fail("contrato", "lista sumiu antes da escolha");
            reply(request, false, null,
                "EQUATORIAL_PORTAL_TIMEOUT: a lista de contratos sumiu antes da escolha do imovel");
            return;
        }
        if (expected.isEmpty()) {
            dialog.recycle();
            closeContractDialog(request, 0,
                "EQUATORIAL_CONTRACT_NOT_FOUND: nenhum imovel configurado para comparar com a lista");
            return;
        }
        Rect window = new Rect();
        dialog.getBoundsInScreen(window);
        int options = countContractOptions(dialog);
        RodLog.step("contrato", "contratos na lista=" + options);
        boolean picked = gestureClickContractDigits(dialog, expected, window);
        RodLog.step("contrato", "toque no imovel despachado=" + picked);
        if (!picked && options == 1) {
            // Login com um unico contrato nao tem ambiguidade: o que esta na lista
            // e o imovel deste acesso. O identificador guardado no cofre nao e o
            // mesmo que o portal usa, e exigir igualdade impediria toda leitura.
            // Com dois ou mais, escolher seria adivinhar de quem e a fatura.
            picked = gestureClickOnlyContract(dialog, window);
            RodLog.step("contrato", "unico contrato adotado=" + picked);
        }
        dialog.recycle();
        if (!picked) {
            // Sem correspondencia nao da para adivinhar qual contrato e o imovel
            // pedido; fechar e falhar e melhor do que ler a fatura de outro.
            closeContractDialog(request, 0, options > 1
                ? "EQUATORIAL_PROPERTY_NOT_MAPPED: a lista tem " + options
                    + " contratos e nenhum corresponde ao imovel configurado"
                : "EQUATORIAL_CONTRACT_NOT_FOUND: o imovel configurado nao aparece na lista de contratos");
            return;
        }
        awaitContractDialogClosed(request, System.currentTimeMillis() + DIALOG_CLOSE_MILLIS);
    }

    /** Gesto despachado nao e item escolhido: quem prova isso e a lista sair da frente. */
    private void awaitContractDialogClosed(String request, long deadline) {
        AccessibilityNodeInfo dialog = contractDialogRoot();
        if (dialog == null) {
            AccessibilityNodeInfo root = packageRoot(CHROME);
            if (root != null) {
                root.recycle();
                RodLog.step("contrato", "lista fechada e portal de volta na frente");
                reply(request, true, new JSONObject(), null);
                return;
            }
        } else {
            dialog.recycle();
        }
        if (System.currentTimeMillis() < deadline) {
            new Handler(Looper.getMainLooper()).postDelayed(
                () -> awaitContractDialogClosed(request, deadline), UI_POLL_MILLIS);
            return;
        }
        closeContractDialog(request, 0,
            "EQUATORIAL_PORTAL_TIMEOUT: a lista de contratos nao fechou depois da escolha");
    }

    /**
     * Encerra o passo com a lista fora da frente. So termina em falha: fechar com
     * BACK cancela a escolha, entao nao ha sucesso possivel por este caminho.
     */
    /** Quantas opcoes a lista oferece. So a contagem; nunca os valores. */
    private static int countContractOptions(AccessibilityNodeInfo node) {
        int total = 0;
        String viewId = node.getViewIdResourceName();
        CharSequence text = node.getText();
        if (viewId != null && viewId.endsWith("id/text1") && text != null && text.length() > 0) total++;
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) { total += countContractOptions(child); child.recycle(); }
        }
        return total;
    }

    /** Toca na unica opcao da lista, quando ela e a unica que existe. */
    private boolean gestureClickOnlyContract(AccessibilityNodeInfo node, Rect window) {
        String viewId = node.getViewIdResourceName();
        CharSequence text = node.getText();
        if (viewId != null && viewId.endsWith("id/text1") && text != null && text.length() > 0
                && node.isVisibleToUser()) {
            Rect bounds = new Rect();
            node.getBoundsInScreen(bounds);
            if (!bounds.isEmpty() && window.contains(bounds.centerX(), bounds.centerY())) {
                Path path = new Path();
                path.moveTo(bounds.exactCenterX(), bounds.exactCenterY());
                return dispatchGesture(new GestureDescription.Builder()
                    .addStroke(new GestureDescription.StrokeDescription(path, 0, 120)).build(), null, null);
            }
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                boolean clicked = gestureClickOnlyContract(child, window);
                child.recycle();
                if (clicked) return true;
            }
        }
        return false;
    }

    private void closeContractDialog(String request, int attempt, String error) {
        AccessibilityNodeInfo dialog = contractDialogRoot();
        if (dialog == null) {
            RodLog.step("contrato", "lista fora da frente na tentativa " + attempt);
            reply(request, false, null, error);
            return;
        }
        dialog.recycle();
        if (attempt >= CONTRACT_CLOSE_ATTEMPTS) {
            RodLog.fail("contrato", "lista nativa continuou aberta apos " + attempt + " tentativas de fechar");
            reply(request, false, null, error);
            return;
        }
        performGlobalAction(GLOBAL_ACTION_BACK);
        new Handler(Looper.getMainLooper()).postDelayed(
            () -> closeContractDialog(request, attempt + 1, error), UI_POLL_MILLIS * 2);
    }

    /**
     * Raiz do dialogo nativo do seletor, ou null quando ele nao esta na frente.
     *
     * Basta "janela ativa que nao e do Chrome" para confundir launcher e
     * notificacao com o seletor, entao os ids do dialogo sao conferidos.
     */
    private AccessibilityNodeInfo contractDialogRoot() {
        AccessibilityNodeInfo active = getRootInActiveWindow();
        if (active == null) {
            RodLog.step("diag", "janela ativa: nenhuma");
            return null;
        }
        // Diagnóstico de forma, nunca de conteúdo: só o nome do pacote dono da
        // janela e quais marcadores de diálogo existem. Descobrir isso por
        // uiautomator não é possível: ele disputa o mesmo canal de
        // acessibilidade e derruba este serviço no meio do fluxo.
        CharSequence owner = active.getPackageName();
        StringBuilder markers = new StringBuilder();
        for (String id : DIALOG_VIEW_IDS) {
            AccessibilityNodeInfo probe = findByViewId(active, id);
            if (probe != null) { probe.recycle(); markers.append(id).append(' '); }
        }
        RodLog.step("diag", "janela ativa pertence a " + (owner == null ? "?" : owner)
            + " | marcadores: " + (markers.length() == 0 ? "nenhum" : markers.toString().trim()));

        // O Chrome desenha o <select> como diálogo do próprio processo, então a
        // janela ainda pertence a ele. Descartar por pacote perdia a lista; o que
        // distingue de fato é a presença dos marcadores do AlertDialog.
        if (markers.length() > 0) return active;
        active.recycle();
        return null;
    }

    /** Ha uma janela do sistema na frente do Chrome? Só nela o BACK e seguro. */
    private boolean systemDialogInFront() {
        AccessibilityNodeInfo active = getRootInActiveWindow();
        if (active == null) return false;
        boolean chrome = belongsTo(active, CHROME);
        active.recycle();
        return !chrome;
    }

    /** Toque no centro de um no ja localizado. */
    private boolean gestureClickNode(AccessibilityNodeInfo node) {
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        if (bounds.isEmpty()) return false;
        Path path = new Path();
        path.moveTo(bounds.exactCenterX(), bounds.exactCenterY());
        return dispatchGesture(new GestureDescription.Builder()
            .addStroke(new GestureDescription.StrokeDescription(path, 0, 120)).build(), null, null);
    }

    /**
     * Espera a pagina assentar num estado reconhecivel e le somente o necessario.
     *
     * dispatchGesture e ACTION_CLICK devolvem true sem que a pagina tenha reagido,
     * entao nao da para confiar no retorno de uma acao: o que vale e reobservar a
     * arvore. Sessao expirada e desafio antibot sao terminais na hora, porque
     * insistir cegamente neles so gasta bateria e atrasa o aviso ao proprietario.
     */
    private void readEquatorial(String request, String expectedUnit) {
        settleEquatorial(request, expectedUnit, System.currentTimeMillis() + PAGE_SETTLE_MILLIS);
    }

    private void settleEquatorial(String request, String expectedUnit, long deadline) {
        try {
            AccessibilityNodeInfo root = packageRoot(CHROME);
            if (root == null) {
                if (System.currentTimeMillis() < deadline) {
                    retryEquatorial(request, expectedUnit, deadline);
                    return;
                }
                reply(request, false, null,
                    "EQUATORIAL_PORTAL_TIMEOUT: o portal nao ficou visivel no Chrome para a leitura");
                return;
            }
            List<String> values = new ArrayList<>();
            collect(root, values);
            root.recycle();
            // O conteudo nunca entra na trilha: a tela carrega valor, vencimento,
            // linha digitavel e PIX.
            EquatorialTextParser.Page page = EquatorialTextParser.parse(String.join("\n", values));

            if (page.state == EquatorialTextParser.State.AUTH_REQUIRED) {
                RodLog.step("equatorial", "portal devolveu a tela de autenticacao");
                reply(request, false, null,
                    "EQUATORIAL_AUTH_REQUIRED: a sessao da Equatorial expirou no Poco");
                return;
            }
            if (page.state == EquatorialTextParser.State.HUMAN_CHECK) {
                RodLog.step("equatorial", "portal exibiu desafio de verificacao humana");
                reply(request, false, null,
                    "EQUATORIAL_HUMAN_CHECK: a Equatorial pediu verificacao humana");
                return;
            }
            if (page.state == EquatorialTextParser.State.NO_BILL) {
                if (System.currentTimeMillis() < deadline) {
                    retryEquatorial(request, expectedUnit, deadline);
                    return;
                }
                RodLog.step("equatorial", "sessao valida, porem sem fatura nesta tela");
                reply(request, false, null,
                    "EQUATORIAL_BILL_NOT_FOUND: nenhuma fatura visivel na tela do imovel");
                return;
            }

            // Confirmar a unidade antes de atribuir a fatura ao imovel pedido.
            // Atribuir por confianca poria a conta de um imovel no nome de outro.
            String shown = page.get("uc").replaceAll("\\D", "");
            String expected = expectedUnit == null ? "" : expectedUnit.replaceAll("\\D", "");
            RodLog.found("equatorial", "unidade na tela", !shown.isEmpty());
            if (shown.isEmpty()) {
                reply(request, false, null,
                    "EQUATORIAL_CONTRACT_NOT_FOUND: a tela nao confirma a unidade consumidora; "
                        + "nao vou atribuir esta fatura");
                return;
            }
            if (!expected.isEmpty() && !shown.equals(expected)) {
                RodLog.fail("equatorial", "a tela mostra outro imovel");
                reply(request, false, null,
                    "EQUATORIAL_CONTRACT_NOT_FOUND: a tela mostra outra unidade consumidora");
                return;
            }

            RodLog.found("equatorial", "valor", !page.get("amount").isEmpty());
            RodLog.found("equatorial", "vencimento", !page.get("due_date").isEmpty());
            RodLog.found("equatorial", "referencia", !page.get("reference").isEmpty());
            RodLog.found("equatorial", "codigo de barras", !page.get("barcode").isEmpty());
            RodLog.found("equatorial", "pix", !page.get("pix").isEmpty());

            JSONObject result = new JSONObject()
                .put("source", "equatorial_chrome_session")
                .put("amount", page.get("amount"))
                .put("due_date", page.get("due_date"))
                .put("reference", page.get("reference"))
                .put("barcode", page.get("barcode"))
                .put("pix", page.get("pix"));
            reply(request, true, result, null);
        } catch (Exception error) {
            reply(request, false, null, error.getClass().getSimpleName() + ": " + error.getMessage());
        }
    }

    private void retryEquatorial(String request, String expectedUnit, long deadline) {
        new Handler(Looper.getMainLooper()).postDelayed(
            () -> settleEquatorial(request, expectedUnit, deadline), PAGE_POLL_MILLIS);
    }

    private static void collectEditors(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> result) {
        if (node.isEditable() || "android.widget.EditText".contentEquals(node.getClassName()))
            result.add(AccessibilityNodeInfo.obtain(node));
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) { collectEditors(child, result); child.recycle(); }
        }
    }

    private static void setNodeText(AccessibilityNodeInfo node, String value) {
        android.os.Bundle arguments = new android.os.Bundle();
        arguments.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value);
        node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments);
    }

    private static boolean clickFirst(AccessibilityNodeInfo node, String... labels) {
        String value = ((node.getText() == null ? "" : node.getText()) + " " +
            (node.getContentDescription() == null ? "" : node.getContentDescription())).toLowerCase();
        for (String label : labels) if (value.contains(label) && node.isClickable())
            return node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                boolean clicked = clickFirst(child, labels);
                child.recycle();
                if (clicked) return true;
            }
        }
        return false;
    }

    private boolean gestureClickLabel(AccessibilityNodeInfo node, String... labels) {
        String value = ((node.getText() == null ? "" : node.getText()) + " " +
            (node.getContentDescription() == null ? "" : node.getContentDescription())).toLowerCase();
        for (String label : labels) {
            if (value.contains(label)) {
                Rect bounds = new Rect();
                node.getBoundsInScreen(bounds);
                if (!bounds.isEmpty()) {
                    Path path = new Path();
                    path.moveTo(bounds.exactCenterX(), bounds.exactCenterY());
                    GestureDescription gesture = new GestureDescription.Builder()
                        .addStroke(new GestureDescription.StrokeDescription(path, 0, 120)).build();
                    return dispatchGesture(gesture, null, null);
                }
            }
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                boolean clicked = gestureClickLabel(child, labels);
                child.recycle();
                if (clicked) return true;
            }
        }
        return false;
    }

    private boolean gestureClickDigits(AccessibilityNodeInfo node, String expected) {
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                boolean clicked = gestureClickDigits(child, expected);
                child.recycle();
                if (clicked) return true;
            }
        }
        String value = digits((node.getText() == null ? "" : node.getText()) + " " +
            (node.getContentDescription() == null ? "" : node.getContentDescription()));
        if (value.contains(expected)) {
            Rect bounds = new Rect();
            node.getBoundsInScreen(bounds);
            if (!bounds.isEmpty()) {
                Path path = new Path();
                path.moveTo(bounds.exactCenterX(), bounds.exactCenterY());
                return dispatchGesture(new GestureDescription.Builder()
                    .addStroke(new GestureDescription.StrokeDescription(path, 0, 120)).build(), null, null);
            }
        }
        return false;
    }

    /**
     * Toca no item cujo numero e exatamente o esperado e que esta mesmo visivel.
     *
     * Duas armadilhas resolvidas aqui. Casar por substring clicava um numero mais
     * longo que apenas contivesse o esperado. E tocar no centro de um item rolado
     * para fora da janela acerta outro lugar da tela, com dispatchGesture devolvendo
     * true nos dois casos.
     *
     * gestureClickDigits fica como esta: o fluxo da Saneago depende do comportamento
     * atual dele e funciona hoje.
     */
    private boolean gestureClickContractDigits(AccessibilityNodeInfo node, String expected, Rect window) {
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                boolean clicked = gestureClickContractDigits(child, expected, window);
                child.recycle();
                if (clicked) return true;
            }
        }
        String value = (node.getText() == null ? "" : node.getText()) + " " +
            (node.getContentDescription() == null ? "" : node.getContentDescription());
        if (!ContractMatch.matches(value, expected)) return false;
        if (!node.isVisibleToUser()) return false;
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        if (bounds.isEmpty()) return false;
        if (!window.isEmpty() && !ContractMatch.centerInside(
                bounds.left, bounds.top, bounds.right, bounds.bottom,
                window.left, window.top, window.right, window.bottom)) return false;
        Path path = new Path();
        path.moveTo(bounds.exactCenterX(), bounds.exactCenterY());
        return dispatchGesture(new GestureDescription.Builder()
            .addStroke(new GestureDescription.StrokeDescription(path, 0, 120)).build(), null, null);
    }

    /**
     * Regras puras de identificacao do contrato. Sem Android, para serem testaveis.
     *
     * Classe aninhada estatica de proposito: carrega-la num teste de JVM nao
     * inicializa o servico de acessibilidade em volta.
     */
    static final class ContractMatch {
        /**
         * Tudo que nao seja digito ou separador interno de um numero quebra o token.
         *
         * Ponto, hifen, espaco e espaco fixo aparecem dentro de um mesmo numero na
         * tela ("1234 5678", "1.234.567-8"); letras e virgula separam numeros
         * diferentes.
         */
        private static final String TOKEN_SEPARATOR = "[^0-9.\\- \\u00a0]+";

        private ContractMatch() { }

        /** So os digitos, sem zeros a esquerda: a tela e o cofre escrevem diferente. */
        static String normalize(String value) {
            if (value == null) return "";
            String result = value.replaceAll("\\D", "");
            return result.replaceFirst("^0+(?!$)", "");
        }

        /**
         * O texto contem o numero esperado inteiro, e nao como pedaco de outro.
         *
         * Comparar token a token e o que impede 123456789 de ser aceito como
         * 12345678 e uma fatura ser atribuida ao imovel errado.
         */
        static boolean matches(String raw, String expected) {
            String target = normalize(expected);
            if (target.isEmpty() || raw == null) return false;
            for (String token : raw.split(TOKEN_SEPARATOR))
                if (normalize(token).equals(target)) return true;
            return false;
        }

        /** O centro do item cai dentro da janela? Fora dela o toque acerta outra coisa. */
        static boolean centerInside(int left, int top, int right, int bottom,
                                    int windowLeft, int windowTop, int windowRight, int windowBottom) {
            if (right <= left || bottom <= top) return false;
            int x = (left + right) / 2;
            int y = (top + bottom) / 2;
            return x >= windowLeft && x <= windowRight && y >= windowTop && y <= windowBottom;
        }
    }

    private static boolean containsDigits(AccessibilityNodeInfo node, String expected) {
        String value = digits((node.getText() == null ? "" : node.getText()) + " " +
            (node.getContentDescription() == null ? "" : node.getContentDescription()));
        if (value.contains(expected)) return true;
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                boolean found = containsDigits(child, expected);
                child.recycle();
                if (found) return true;
            }
        }
        return false;
    }

    private static boolean containsLabel(AccessibilityNodeInfo node, String label) {
        String value = ((node.getText() == null ? "" : node.getText()) + " " +
            (node.getContentDescription() == null ? "" : node.getContentDescription())).toLowerCase();
        if (value.contains(label)) return true;
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                boolean found = containsLabel(child, label);
                child.recycle();
                if (found) return true;
            }
        }
        return false;
    }

    private static String digits(String value) {
        return ContractMatch.normalize(value);
    }

    private JSONObject readSaneago() throws Exception {
        AccessibilityNodeInfo root = saneagoRoot();
        if (root == null) throw new IllegalStateException("Janela Saneago nao encontrada");
        List<String> text = new ArrayList<>();
        collect(root, text);
        root.recycle();
        for (String value : text) {
            String normalized = value.toLowerCase();
            if (normalized.contains("faça login") || normalized.contains("faca login") ||
                    normalized.contains("abrir tela de login"))
                throw new IllegalStateException("Sessao Saneago expirada");
        }
        JSONObject result = new JSONObject()
            .put("source", "saneago_android_app")
            .put("account", valueAfterPrefix(text, "Conta:"))
            .put("amount", valueAfter(text, "Fatura atual"))
            .put("reference", valueAfter(text, "Referencia", "Referência"))
            .put("due_date", valueAfter(text, "Vencimento"))
            .put("consumption", valueAfter(text, "Consumo"))
            .put("read_only", true);
        if (result.getString("account").isEmpty() || result.getString("amount").isEmpty() ||
                result.getString("reference").isEmpty() || result.getString("due_date").isEmpty() ||
                result.getString("consumption").isEmpty())
            throw new IllegalStateException("Campos financeiros ainda indisponiveis");
        return result;
    }

    private void readSaneagoWithFallback(String request) {
        try {
            reply(request, true, readSaneago(), null);
        } catch (Exception error) {
            if (error.getMessage() != null && error.getMessage().contains("Sessao Saneago expirada")) {
                reply(request, false, null, error.getMessage());
                return;
            }
            readSaneagoOcr(request);
        }
    }

    private void readSaneagoOcr(String request) {
        readSaneagoOcr(request, true);
    }

    private void readSaneagoOcr(String request, boolean allowLoginRecovery) {
        takeScreenshot(Display.DEFAULT_DISPLAY, getMainExecutor(), new TakeScreenshotCallback() {
            @Override public void onSuccess(ScreenshotResult screenshot) {
                HardwareBuffer buffer = screenshot.getHardwareBuffer();
                ColorSpace colorSpace = screenshot.getColorSpace();
                Bitmap hardware = Bitmap.wrapHardwareBuffer(buffer, colorSpace);
                if (hardware == null) {
                    buffer.close();
                    reply(request, false, null, "Screenshot sem bitmap");
                    return;
                }
                Bitmap bitmap = hardware.copy(Bitmap.Config.ARGB_8888, false);
                buffer.close();
                TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
                    .process(InputImage.fromBitmap(bitmap, 0))
                    .addOnSuccessListener(text -> {
                        if (allowLoginRecovery && clickLoginRecovery(text)) {
                            bitmap.recycle();
                            new Handler(Looper.getMainLooper()).postDelayed(
                                () -> readSaneagoOcr(request, false), 8000
                            );
                            return;
                        }
                        String normalized = text.getText() == null ? "" : text.getText().toLowerCase();
                        if (!allowLoginRecovery && normalized.contains("abrir tela de login")) {
                            bitmap.recycle();
                            reply(request, false, null, "Sessao Saneago expirada; refaca o login no app oficial");
                            return;
                        }
                        try { reply(request, true, parseOcr(text.getText()), null); }
                        catch (Exception error) {
                            String raw = text.getText() == null ? "" : text.getText();
                            String metrics = " chars=" + raw.length() +
                                " conta=" + raw.toLowerCase().contains("conta") +
                                " fatura=" + raw.toLowerCase().contains("fatura") +
                                " consumo=" + raw.toLowerCase().contains("consumo");
                            reply(request, false, null, error.getMessage() + metrics);
                        }
                        finally { bitmap.recycle(); }
                    })
                    .addOnFailureListener(error -> {
                        bitmap.recycle();
                        reply(request, false, null, "OCR indisponivel: " + error.getClass().getSimpleName());
                    });
            }
            @Override public void onFailure(int errorCode) {
                reply(request, false, null, "Screenshot falhou: " + errorCode);
            }
        });
    }

    private boolean clickLoginRecovery(Text text) {
        for (Text.TextBlock block : text.getTextBlocks()) {
            for (Text.Line line : block.getLines()) {
                String value = line.getText().toLowerCase();
                Rect bounds = line.getBoundingBox();
                if (bounds != null && value.contains("abrir tela de login")) {
                    Path path = new Path();
                    path.moveTo(bounds.exactCenterX(), bounds.exactCenterY());
                    GestureDescription gesture = new GestureDescription.Builder()
                        .addStroke(new GestureDescription.StrokeDescription(path, 0, 120)).build();
                    return dispatchGesture(gesture, null, null);
                }
            }
        }
        return false;
    }

    static JSONObject parseOcr(String raw) throws Exception {
        Map<String, String> values = SaneagoOcrParser.parse(raw);
        JSONObject result = new JSONObject().put("source", "saneago_android_ocr").put("read_only", true);
        for (Map.Entry<String, String> entry : values.entrySet()) result.put(entry.getKey(), entry.getValue());
        return result;
    }

    private AccessibilityNodeInfo saneagoRoot() {
        return packageRoot(SANEAGO);
    }

    private AccessibilityNodeInfo packageRoot(String packageName) {
        AccessibilityNodeInfo active = getRootInActiveWindow();
        if (belongsTo(active, packageName)) return active;
        if (active != null) active.recycle();
        for (AccessibilityWindowInfo window : getWindows()) {
            AccessibilityNodeInfo root = window.getRoot();
            if (belongsTo(root, packageName)) return root;
            if (root != null) root.recycle();
        }
        return null;
    }

    private static boolean belongsToSaneago(AccessibilityNodeInfo root) {
        return belongsTo(root, SANEAGO);
    }

    private static boolean belongsTo(AccessibilityNodeInfo root, String packageName) {
        return root != null && root.getPackageName() != null && packageName.contentEquals(root.getPackageName());
    }

    private void reply(String request, boolean ok, JSONObject payload, String error) {
        if (ok) RodLog.step("resposta", "ok");
        else RodLog.fail("resposta", "falha: " + error);
        getSharedPreferences(PREFS_BRIDGE, MODE_PRIVATE).edit()
            .putString("request_id", request).putBoolean("ok", ok)
            .putString("payload", payload == null ? "{}" : payload.toString())
            .putString("error", error == null ? "" : error.substring(0, Math.min(error.length(), 180))).apply();
    }

    private static void collect(AccessibilityNodeInfo node, List<String> values) {
        CharSequence text = node.getText();
        if (text != null && text.length() > 0) values.add(text.toString().trim());
        CharSequence description = node.getContentDescription();
        if (description != null && description.length() > 0) values.add(description.toString().trim());
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) { collect(child, values); child.recycle(); }
        }
    }
    private static String valueAfterPrefix(List<String> values, String prefix) {
        for (String value : values) if (value.startsWith(prefix)) return value.substring(prefix.length()).trim();
        return "";
    }
    private static String valueAfter(List<String> values, String... labels) {
        for (int i = 0; i < values.size() - 1; i++)
            for (String label : labels) if (values.get(i).equalsIgnoreCase(label)) return values.get(i + 1);
        return "";
    }
}
