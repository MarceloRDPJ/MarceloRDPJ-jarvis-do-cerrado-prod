package br.com.jarviscerrado.poco;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Religa o {@link AgentService} sem que ninguém toque na tela.
 *
 * O Poco é servidor doméstico: ninguém está do lado dele. Este receiver cobria
 * apenas {@code BOOT_COMPLETED}, então o {@code adb install -r} — que mata o
 * processo do app para substituí-lo — deixava o nó offline no Pi até alguém
 * abrir o aplicativo com a mão. O sistema rebindava o serviço de acessibilidade
 * sozinho, mas nada rebindava o agente: o {@code dumpsys activity services}
 * mostrava só o {@code JarvisAccessibilityService}.
 *
 * {@code MY_PACKAGE_REPLACED} é a contraparte oficial de {@code BOOT_COMPLETED}
 * para reinstalação: o PackageManager o entrega ao próprio pacote substituído e
 * o Android 12 o lista, junto de {@code BOOT_COMPLETED}, entre as isenções que
 * permitem iniciar serviço em primeiro plano a partir do segundo plano. É o
 * menor mecanismo que fecha o caso: nenhum componente novo, nenhuma permissão
 * nova, nenhuma dependência nova — só a ação que faltava no filtro que já
 * existia.
 */
public class BootReceiver extends BroadcastReceiver {

    /**
     * As duas únicas ações que devem religar o agente.
     *
     * Deliberadamente estreito. {@code ACTION_PACKAGE_REPLACED} fala de outros
     * pacotes (Chrome, Saneago, Equatorial atualizando) e não é motivo para
     * mexer no agente; {@code MY_PACKAGE_REPLACED} fala do próprio agente.
     */
    static boolean shouldStartAgent(String action) {
        return Intent.ACTION_BOOT_COMPLETED.equals(action)
            || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action);
    }

    /** Rótulo da causa para a trilha `adb logcat -s ROD`, que é a prova no aparelho. */
    static String cause(String action) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(action)) return "boot";
        if (Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) return "reinstalacao";
        return "acao-ignorada";
    }

    @Override public void onReceive(Context context, Intent intent) {
        String action = intent == null ? null : intent.getAction();
        if (!shouldStartAgent(action)) {
            RodLog.step("autostart", "ignorado: " + cause(action) + " (" + action + ")");
            return;
        }
        // O agente sobe mesmo sem endpoint configurado: um nó que subiu e ainda
        // não tem para quem falar é diagnosticável; um nó que não subiu é ausência.
        boolean started = AgentService.start(context);
        RodLog.step("autostart", "causa=" + cause(action) + " servico_iniciado=" + started);
    }
}
