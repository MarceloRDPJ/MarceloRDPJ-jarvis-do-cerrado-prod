import logging
from typing import Dict, Any, Optional

from database.persistence import Persistence
from core.events import Event
from core.context import ContextEngine
from core.context_reader import ContextReader

from modules.system import SystemModule
from modules.network import NetworkModule
from modules.reminders import set_reminder_job

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

        # ---------------- CHAT ----------------
        if intent == "chat":
            return params.get(
                "response",
                "Uai… pode falar. Tô te ouvindo."
            )

        # ---------------- GREET / HELP ----------------
        if intent == "greet":
            return "👋 E aí, Marcelo. Jarvis do Cerrado online."

        if intent == "help":
            return (
                "🧠 *Posso te ajudar com:*\n"
                "- status do sistema\n"
                "- quem tá na rede\n"
                "- lembretes\n"
                "- mudou algo hoje?\n"
                "- isso é normal?\n"
                "- bloqueios e segurança\n"
            )

        # ---------------- SYSTEM ----------------
        if intent == "system_status":
            return await SystemModule.get_status()

        if intent == "system_reboot":
            return SystemModule.reboot_device()

        # ---------------- NETWORK ----------------
        if intent == "network_scan":
            return await NetworkModule.scan_network()

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
            text = params.get("text", "Lembrete")
            minutes = int(params.get("minutes", 1))
            repeat = bool(params.get("repeat", False))

            Persistence.add_task(
                chat_id=chat_id,
                text=text,
                due_timestamp=minutes * 60,
                repeat=repeat,
                interval_minutes=minutes,
            )

            set_reminder_job(
                self.app,
                chat_id,
                text,
                minutes,
                repeat,
            )

            return f"⏰ Certo. Vou te lembrar de: *{text}*."

        # ---------------- FUTUROS ----------------
        if intent == "energy_status":
            return "⚡ Monitoramento de energia em fase de coleta."

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
