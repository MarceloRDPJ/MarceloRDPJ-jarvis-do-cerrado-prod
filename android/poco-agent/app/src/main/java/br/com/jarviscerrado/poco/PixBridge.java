package br.com.jarviscerrado.poco;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.graphics.Path;
import android.graphics.Rect;
import android.hardware.HardwareBuffer;
import android.os.Handler;
import android.os.Looper;
import android.view.Display;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONObject;

/**
 * Passo de acessibilidade que aciona o PIX da linha certa e le o QR.
 *
 * Mora fora do serviço de acessibilidade de propósito: o serviço pertence a
 * outro fluxo e a outro dono, e enxertar um segundo fluxo dentro dele
 * multiplicaria os pontos de conflito. Tudo aqui usa apenas API pública de
 * {@link AccessibilityService} — árvore, gesto e captura de tela — e devolve o
 * resultado por callback, para que a ponte precise de poucas linhas.
 *
 * A regra que da razao de existir a este arquivo: acionar "o primeiro QR da
 * pagina" funciona enquanto ha uma unica fatura em aberto e entrega o Pix do mes
 * errado no primeiro mes com duas. O controle acionado e o da linha cuja
 * referencia casa com a pedida, e ambiguidade e recusa.
 *
 * O payload nunca e registrado. A trilha diz se leu, nao o que leu.
 */
final class PixBridge {

    interface Reply {
        void ok(JSONObject payload);
        void fail(String error);
    }

    private static final String CHROME = "com.android.chrome";
    /** Prazo para a linha da fatura pedida aparecer na arvore. */
    private static final long ROW_DEADLINE_MILLIS = 15_000L;
    /** Prazo para o QR renderizar e ser decodificado depois do toque. */
    private static final long QR_DEADLINE_MILLIS = 20_000L;
    private static final long POLL_MILLIS = 500L;
    /**
     * Intervalo entre capturas de tela.
     *
     * takeScreenshot tem limite de taxa no proprio sistema: pedir de novo antes
     * disso volta com erro de intervalo curto, que seria lido como "sem QR".
     */
    private static final long SCREENSHOT_INTERVAL_MILLIS = 1_200L;
    /** Niveis de ancestral consultados para descobrir a linha de um controle. */
    private static final int ROW_DEPTH = 6;

    private PixBridge() { }

    static void pixPayload(AccessibilityService service, String reference, Reply reply) {
        awaitRow(service, reference, reply, System.currentTimeMillis() + ROW_DEADLINE_MILLIS);
    }

    private static void awaitRow(AccessibilityService service, String reference,
                                 Reply reply, long deadline) {
        AccessibilityNodeInfo page = chromeRoot(service);
        if (page == null) {
            if (System.currentTimeMillis() < deadline) {
                retry(() -> awaitRow(service, reference, reply, deadline), POLL_MILLIS);
                return;
            }
            reply.fail("EQUATORIAL_PORTAL_TIMEOUT: o portal nao ficou visivel para acionar o Pix");
            return;
        }

        Candidates candidates = collect(page, reference);
        page.recycle();
        if (candidates.error != null) {
            candidates.release();
            reply.fail(candidates.error);
            return;
        }
        AccessibilityNodeInfo target = candidates.chosen();
        if (target == null) {
            candidates.release();
            if (System.currentTimeMillis() < deadline) {
                retry(() -> awaitRow(service, reference, reply, deadline), POLL_MILLIS);
                return;
            }
            reply.fail("EQUATORIAL_PIX_NOT_FOUND: nao ha controle de Pix na linha da fatura pedida");
            return;
        }

        boolean tapped = tapCenter(service, target);
        RodLog.step("pix", "controle da linha acionado=" + tapped);
        candidates.release();
        if (!tapped) {
            if (System.currentTimeMillis() < deadline) {
                retry(() -> awaitRow(service, reference, reply, deadline), POLL_MILLIS);
                return;
            }
            reply.fail("EQUATORIAL_PIX_NOT_FOUND: o controle de Pix da linha nao aceitou o toque");
            return;
        }
        awaitQr(service, reply, System.currentTimeMillis() + QR_DEADLINE_MILLIS);
    }

    /**
     * Captura a tela e decodifica. Enquanto houver prazo, tentar de novo e
     * correto: o QR aparece por JavaScript e pode nao estar pronto na primeira
     * captura.
     */
    private static void awaitQr(AccessibilityService service, Reply reply, long deadline) {
        service.takeScreenshot(Display.DEFAULT_DISPLAY, service.getMainExecutor(),
            new AccessibilityService.TakeScreenshotCallback() {
                @Override public void onSuccess(AccessibilityService.ScreenshotResult screenshot) {
                    HardwareBuffer buffer = screenshot.getHardwareBuffer();
                    ColorSpace colorSpace = screenshot.getColorSpace();
                    Bitmap hardware = Bitmap.wrapHardwareBuffer(buffer, colorSpace);
                    if (hardware == null) {
                        buffer.close();
                        again(service, reply, deadline, "EQUATORIAL_PIX_NOT_FOUND: captura de tela sem imagem");
                        return;
                    }
                    Bitmap bitmap = hardware.copy(Bitmap.Config.ARGB_8888, false);
                    buffer.close();
                    PixQrReader.decode(bitmap, new PixQrReader.Callback() {
                        @Override public void onPayload(String payload) {
                            bitmap.recycle();
                            try {
                                reply.ok(new JSONObject().put("pix", payload));
                            } catch (Exception error) {
                                reply.fail("EQUATORIAL_PIX_INVALID: falha ao montar a resposta do Pix");
                            }
                        }
                        @Override public void onError(String message) {
                            bitmap.recycle();
                            again(service, reply, deadline, message);
                        }
                    });
                }
                @Override public void onFailure(int errorCode) {
                    again(service, reply, deadline,
                        "EQUATORIAL_PIX_NOT_FOUND: captura de tela falhou (" + errorCode + ")");
                }
            });
    }

    /**
     * Nova tentativa enquanto houver prazo.
     *
     * Ambiguidade nao se resolve tentando de novo: dois QR diferentes na tela
     * continuarao dois, e insistir so atrasaria o aviso.
     */
    private static void again(AccessibilityService service, Reply reply, long deadline, String message) {
        boolean fatal = message != null && message.contains("EQUATORIAL_PIX_AMBIGUOUS");
        if (!fatal && System.currentTimeMillis() < deadline) {
            retry(() -> awaitQr(service, reply, deadline), SCREENSHOT_INTERVAL_MILLIS);
            return;
        }
        reply.fail(message == null ? "EQUATORIAL_PIX_NOT_FOUND: nenhum Pix legivel na tela" : message);
    }

    // ------------------------------------------------------------ arvore

    /** Controles clicaveis das linhas cuja referencia casa com a pedida. */
    private static Candidates collect(AccessibilityNodeInfo page, String reference) {
        Candidates result = new Candidates();
        List<AccessibilityNodeInfo> clickable = new ArrayList<>();
        collectClickable(page, clickable);

        List<String> labels = new ArrayList<>();
        List<AccessibilityNodeInfo> inRow = new ArrayList<>();
        for (AccessibilityNodeInfo node : clickable) {
            if (!PixRowLocator.matchesReference(rowText(node), reference)) {
                node.recycle();
                continue;
            }
            inRow.add(node);
            labels.add(label(node));
        }
        if (inRow.isEmpty()) return result;

        int chosen = PixRowLocator.preferPixLabel(labels);
        if (chosen == PixRowLocator.AMBIGUOUS) {
            for (AccessibilityNodeInfo node : inRow) node.recycle();
            result.error = "EQUATORIAL_PIX_AMBIGUOUS: a linha da fatura tem mais de um controle de Pix";
            return result;
        }
        if (chosen == PixRowLocator.NOT_FOUND) {
            // Sem rotulo reconhecivel, vale a coluna mais a direita: a de
            // pagamento via PIX e a ultima das quatro.
            chosen = rightmost(inRow);
        }
        for (int i = 0; i < inRow.size(); i++) {
            if (i == chosen) result.target = inRow.get(i);
            else inRow.get(i).recycle();
        }
        return result;
    }

    private static final class Candidates {
        AccessibilityNodeInfo target;
        String error;

        AccessibilityNodeInfo chosen() { return target; }

        void release() {
            if (target != null) { target.recycle(); target = null; }
        }
    }

    private static int rightmost(List<AccessibilityNodeInfo> nodes) {
        int index = 0;
        int best = Integer.MIN_VALUE;
        for (int i = 0; i < nodes.size(); i++) {
            Rect bounds = new Rect();
            nodes.get(i).getBoundsInScreen(bounds);
            if (bounds.centerX() > best) { best = bounds.centerX(); index = i; }
        }
        return index;
    }

    /** Texto do ancestral mais proximo que carrega uma referencia de fatura. */
    private static String rowText(AccessibilityNodeInfo node) {
        AccessibilityNodeInfo current = AccessibilityNodeInfo.obtain(node);
        String fallback = "";
        for (int level = 0; level < ROW_DEPTH && current != null; level++) {
            List<String> texts = new ArrayList<>();
            collectText(current, texts);
            String joined = String.join(" ", texts);
            if (!PixRowLocator.normalizeReference(joined).isEmpty()) {
                current.recycle();
                return joined;
            }
            fallback = joined;
            AccessibilityNodeInfo parent = current.getParent();
            current.recycle();
            current = parent;
        }
        if (current != null) current.recycle();
        return fallback;
    }

    private static String label(AccessibilityNodeInfo node) {
        String text = node.getText() == null ? "" : node.getText().toString();
        String description = node.getContentDescription() == null
            ? "" : node.getContentDescription().toString();
        String tooltip = node.getTooltipText() == null ? "" : node.getTooltipText().toString();
        return (text + " " + description + " " + tooltip).trim();
    }

    private static void collectClickable(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> out) {
        if (node.isClickable()) out.add(AccessibilityNodeInfo.obtain(node));
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) { collectClickable(child, out); child.recycle(); }
        }
    }

    private static void collectText(AccessibilityNodeInfo node, List<String> out) {
        CharSequence text = node.getText();
        if (text != null && text.length() > 0) out.add(text.toString().trim());
        CharSequence description = node.getContentDescription();
        if (description != null && description.length() > 0) out.add(description.toString().trim());
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) { collectText(child, out); child.recycle(); }
        }
    }

    /**
     * Raiz do Chrome, inclusive quando a janela ativa e outra.
     *
     * Mesma logica do serviço, repetida porque aquele metodo e privado e o
     * arquivo tem outro dono.
     */
    static AccessibilityNodeInfo chromeRoot(AccessibilityService service) {
        AccessibilityNodeInfo active = service.getRootInActiveWindow();
        if (belongsToChrome(active)) return active;
        if (active != null) active.recycle();
        for (AccessibilityWindowInfo window : service.getWindows()) {
            AccessibilityNodeInfo root = window.getRoot();
            if (belongsToChrome(root)) return root;
            if (root != null) root.recycle();
        }
        return null;
    }

    private static boolean belongsToChrome(AccessibilityNodeInfo root) {
        return root != null && root.getPackageName() != null
            && CHROME.contentEquals(root.getPackageName());
    }

    /** Toque no centro do no; fora da viewport, pede para trazer e devolve falso. */
    private static boolean tapCenter(AccessibilityService service, AccessibilityNodeInfo node) {
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        if (bounds.isEmpty() || !node.isVisibleToUser()) {
            node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SHOW_ON_SCREEN.getId());
            return false;
        }
        Path path = new Path();
        path.moveTo(bounds.exactCenterX(), bounds.exactCenterY());
        GestureDescription gesture = new GestureDescription.Builder()
            .addStroke(new GestureDescription.StrokeDescription(path, 0, 120)).build();
        return service.dispatchGesture(gesture, null, null);
    }

    static void retry(Runnable action, long delayMillis) {
        new Handler(Looper.getMainLooper()).postDelayed(action, delayMillis);
    }
}
