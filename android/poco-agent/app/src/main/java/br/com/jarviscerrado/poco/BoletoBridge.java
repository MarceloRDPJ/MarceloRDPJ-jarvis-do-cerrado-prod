package br.com.jarviscerrado.poco;

import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityNodeInfo;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONObject;

/**
 * Descobre QUAL fatura da lista o download deve trazer.
 *
 * A célula de download da página aponta
 * "mostrarFaturaCodigoBarras.aspx?invoice=N", e N é a posição da linha na
 * tabela. A árvore de acessibilidade não expõe href nem onclick, mas expõe os
 * textos na ordem em que a página os desenha — e a referência aparece uma vez
 * por linha. Contar referências na ordem dá o N sem depender de o Chrome expor
 * estrutura de tabela, que ele não expõe de forma estável.
 *
 * Nada é baixado aqui. Este passo só responde um número; quem baixa é
 * {@link BoletoDownloader}, com a sessão do WebView do próprio ROD.
 */
final class BoletoBridge {
    private static final long ROW_DEADLINE_MILLIS = 15_000L;
    private static final long POLL_MILLIS = 500L;

    private BoletoBridge() { }

    static void invoiceIndex(AccessibilityService service, String reference, PixBridge.Reply reply) {
        await(service, reference, reply, System.currentTimeMillis() + ROW_DEADLINE_MILLIS);
    }

    private static void await(AccessibilityService service, String reference,
                              PixBridge.Reply reply, long deadline) {
        AccessibilityNodeInfo page = PixBridge.chromeRoot(service);
        if (page == null) {
            if (System.currentTimeMillis() < deadline) {
                PixBridge.retry(() -> await(service, reference, reply, deadline), POLL_MILLIS);
                return;
            }
            reply.fail("EQUATORIAL_PORTAL_TIMEOUT: o portal nao ficou visivel para localizar o boleto");
            return;
        }
        List<String> texts = new ArrayList<>();
        collectText(page, texts);
        page.recycle();

        int index = PixRowLocator.invoiceIndex(texts, reference);
        RodLog.step("boleto", "linha da fatura localizada indice=" + index);
        if (index >= 0) {
            try {
                reply.ok(new JSONObject().put("invoice_index", index));
            } catch (Exception error) {
                reply.fail("EQUATORIAL_BOLETO_NOT_FOUND: falha ao montar a resposta do boleto");
            }
            return;
        }
        if (index == PixRowLocator.AMBIGUOUS) {
            // Sem referencia pedida e com mais de uma fatura em aberto, escolher
            // seria adivinhar qual boleto o proprietario quer.
            reply.fail("EQUATORIAL_BILL_NOT_FOUND: ha mais de uma fatura em aberto; diga a referencia");
            return;
        }
        if (System.currentTimeMillis() < deadline) {
            PixBridge.retry(() -> await(service, reference, reply, deadline), POLL_MILLIS);
            return;
        }
        reply.fail("EQUATORIAL_BILL_NOT_FOUND: a fatura pedida nao esta na lista de segunda via");
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
}
