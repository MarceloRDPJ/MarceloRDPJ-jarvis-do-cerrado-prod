import logging
from typing import Dict, Any

from jarvis.database.persistence import Persistence
from jarvis.core.events import Event
from jarvis.core.context import ContextEngine
from jarvis.core.context_reader import ContextReader
from jarvis.core.flows import RemindersFlow
from jarvis.core.personality import Personality

from jarvis.modules.system import SystemModule
from jarvis.modules.network import NetworkModule
# from jarvis.modules.reminders import set_reminder_job # Deprecated in favor of Scheduler

logger = logging.getLogger("core.executor")


class Executor:
    """
    Executor do Jarvis do Cerrado — EXECUÇÃO CONTROLADA

    PRINCÍPIOS ABSOLUTOS (NUNCA VIOLAR):
    - Executor NÃO interpreta linguagem
    - Executor NÃO decide intenção
    - Executor NÃO faz heurística
    - Executor SOMENTE executa ações explícitas
    - Ações perigosas exigem confirmação
    - Tudo é registrado
    """

    def __init__(self, application):
        self.app = application

        # Inicialização idempotente
        Persistence.init_db()

        # Armazena ação pendente por chat
        self.pending_actions: Dict[int, Dict[str, Any]] = {}

        logger.info("Executor inicializado com sucesso.")

    # =====================================================
    # EXECUÇÃO PRINCIPAL
    # =====================================================
    async def execute(self, intent_data: Dict[str, Any], chat_id: int) -> str:
        """
        Executa UMA intenção já resolvida.
        """

        # -----------------------------
        # VALIDAÇÃO
        # -----------------------------
        if not isinstance(intent_data, dict):
            logger.error("Intent inválida (estrutura incorreta)")
            return "❌ Comando inválido."

        intent: str = intent_data.get("intent")
        action: str = intent_data.get("action", "default")
        params: Dict[str, Any] = intent_data.get("params", {})
        requires_confirmation: bool = intent_data.get(
            "requires_confirmation", False
        )

        logger.info(f"Executor → intent={intent} | action={action}")

        # -----------------------------
        # LOG DE EVENTO (MEMÓRIA LONGA)
        # -----------------------------
        try:
            Persistence.log_event(
                Event(
                    type=f"{intent}.{action}",
                    source="executor",
                    payload=intent_data,
                )
            )
        except Exception:
            logger.exception("Erro ao registrar evento")

        # -----------------------------
        # CONTEXTO (MEMÓRIA CURTA)
        # -----------------------------
        try:
            ContextEngine.save_context(chat_id, intent_data)
        except Exception:
            logger.exception("Erro ao salvar contexto")

        # =====================================================
        # CONFIRMAÇÃO / CANCELAMENTO (PASSO 10)
        # =====================================================
        if intent == "action_confirm":
            return await self._confirm_action(chat_id)

        if intent == "action_cancel":
            return self._cancel_action(chat_id)

        # =====================================================
        # AÇÕES QUE EXIGEM CONFIRMAÇÃO
        # =====================================================
        if requires_confirmation:
            self.pending_actions[chat_id] = intent_data
            return (
                "⚠️ *Ação sensível detectada.*\n\n"
                "Digite **confirmar** para executar\n"
                "ou **cancelar** para abortar."
            )

        # =====================================================
        # EXECUÇÃO NORMAL
        # =====================================================
        return await self._execute_intent(intent, action, params, chat_id)

    # =====================================================
    # EXECUTOR INTERNO
    # =====================================================
    async def _execute_intent(
        self,
        intent: str,
        action: str,
        params: Dict[str, Any],
        chat_id: int,
    ) -> str:

        # ---------------- FLOW INPUT ----------------
        if intent == "flow_input":
            # Delega para o fluxo ativo
            ctx = ContextEngine.get_context(chat_id)
            return RemindersFlow.handle_response(chat_id, params.get("text"), ctx)

        # ---------------- CHAT ----------------
        if intent == "chat":
            return params.get(
                "response",
                Personality.get_response("FALLBACK")
            )

        # ---------------- SMALL TALK ----------------
        if intent == "small_talk":
            return Personality.get_small_talk(params.get("text", ""))

        # ---------------- IDENTITY ----------------
        if intent == "identity_who":
            return Personality.get_response("IDENTITY_WHO")

        if intent == "identity_capabilities":
            return Personality.get_response("IDENTITY_CAPABILITIES")

        # ---------------- GREET / HELP ----------------
        if intent == "greet":
            return Personality.get_response("GREET")

        if intent == "help":
            return (
                "🧠 *Menu de Ajuda do Jarvis*\n\n"
                "Aqui está o que eu posso fazer por você:\n\n"
                "🌐 *Rede & Dispositivos*\n"
                "- *\"Quem tá na rede?\"* - Mostra dispositivos conectados.\n"
                "- *\"Mudar o nome do 192.168.1.X para TV Sala\"* - Organiza sua rede.\n"
                "- *\"Status da internet\"* - Faz um teste de velocidade.\n\n"
                "⏰ *Lembretes & Tarefas*\n"
                "- *\"Me lembre de tomar remédio a cada 8 horas\"* - Cria lembretes recorrentes.\n"
                "- *\"Me lembre no sábado as 14h\"* - Agenda compromissos.\n"
                "- *\"Me lembre de beber água\"* - Ativa o modo hidratação.\n\n"
                "💧 *Saúde & Hidratação*\n"
                "- *\"Quantas águas eu bebi?\"* - Mostra seu progresso diário.\n\n"
                "🖥️ *Sistema & Segurança*\n"
                "- *\"Status do sistema\"* - Mostra uso de CPU, memória e temperatura.\n"
                "- *\"Reiniciar sistema\"* - (Cuidado) Reinicia o servidor.\n\n"
                "💬 *Conversa*\n"
                "- Eu entendo linguagem natural, então pode falar do seu jeito!\n"
                "- Se eu não entender, vou perguntar.\n\n"
                "É só chamar! 👊"
            )

        # ---------------- SYSTEM ----------------
        if intent == "system_status":
            return await SystemModule.get_status()

        if intent == "system_reboot":
            return SystemModule.reboot_device()

        # ---------------- NETWORK ----------------
        if intent == "network_scan":
            return await NetworkModule.scan_network()

        if intent == "network_rename":
            target = params.get("target") # IP
            new_name = params.get("name")

            # Precisamos do MAC para salvar. NetworkModule não expõe fácil o MAC pelo IP ainda.
            # Vamos fazer um scan rápido (cacheado idealmente) ou ler do raw snapshot.
            raw = await NetworkModule.get_raw_status_snapshot_internal() # Método novo necessário ou usar scan_network_human_sync modificado
            # Simplificação: Vamos implementar helper no NetworkModule para pegar MAC pelo IP
            mac = await NetworkModule.resolve_mac_by_ip(target)

            if mac and new_name:
                Persistence.set_device_name(mac, new_name)
                return f"✅ Dispositivo {target} agora é conhecido como *{new_name}*."
            elif not mac:
                return f"❌ Não encontrei o IP {target} na rede agora."
            else:
                return "❌ Preciso do IP e do novo nome. Ex: mudar nome do 192.168.1.5 para TV Sala"

        if intent == "network_block_device":
            return "🚫 Bloqueio de dispositivo ainda não conectado ao AdGuard."

        if intent == "network_block_site":
            return "🚫 Bloqueio de site ainda não conectado ao AdGuard."

        # ---------------- CONTEXT (PASSO 6) ----------------
        if intent == "context_query":
            try:
                result = ContextReader.handle(params)
                return f"📊 Resultado técnico:\n```{result}```"
            except Exception:
                logger.exception("Erro no ContextReader")
                return "❌ Erro ao analisar histórico."

        # ---------------- REMINDERS ----------------
        if intent == "reminder_set":
            if action == "create_request":
                # Inicia fluxo interativo
                return RemindersFlow.start_flow(chat_id, params)
            else:
                # Fallback antigo ou direto
                return "Modo de criação direta descontinuado. Use fluxo interativo."

        # ---------------- FUTUROS ----------------
        if intent == "energy_status":
            return "⚡ Monitoramento de energia em fase de coleta."

        if intent == "hydration_status":
            count = Persistence.get_hydration_count_today(chat_id)
            # Assumindo meta padrão de 2000ml e copo de 250ml se não tiver config
            # Idealmente leríamos a meta do usuário do banco, mas tasks de hidratação têm meta.
            # Vamos simplificar: mostrar contagem de copos/garrafas.

            # Buscar meta da última tarefa de hidratação ativa se houver
            tasks = Persistence.get_tasks_by_action(chat_id, "hydration")
            meta_ml = 2000
            cup_ml = 250
            if tasks:
                import json
                meta_data = json.loads(tasks[0].get("meta", "{}"))
                meta_ml = meta_data.get("meta_ml", 2000)
                cup_ml = meta_data.get("cup_ml", 250)

            total_ml = count * cup_ml
            percentage = int((total_ml / meta_ml) * 100)

            return (
                f"💧 **Hidratação Hoje**\n"
                f"Copos bebidos: {count}\n"
                f"Total aproximado: {total_ml}ml / {meta_ml}ml\n"
                f"Progresso: {percentage}%"
            )

        if intent == "automation_create":
            return "🤖 Automação registrada. Vou observar."

        # ---------------- FALLBACK ----------------
        logger.warning(f"Intent não tratada pelo Executor: {intent}")
        return "🤖 Ainda não sei executar isso… mas já anotei."

    # =====================================================
    # CONFIRMAÇÃO DE AÇÃO
    # =====================================================
    async def _confirm_action(self, chat_id: int) -> str:
        pending = self.pending_actions.pop(chat_id, None)

        if not pending:
            return "⚠️ Nenhuma ação pendente para confirmar."

        logger.info(f"Ação confirmada pelo usuário: {pending}")

        return await self._execute_intent(
            pending.get("intent"),
            pending.get("action", "default"),
            pending.get("params", {}),
            chat_id,
        )

    # =====================================================
    # CANCELAMENTO DE AÇÃO
    # =====================================================
    def _cancel_action(self, chat_id: int) -> str:
        if chat_id in self.pending_actions:
            self.pending_actions.pop(chat_id)
            logger.info("Ação pendente cancelada pelo usuário")
            return "🛑 Ação cancelada com sucesso."

        return "⚠️ Nenhuma ação pendente para cancelar."
