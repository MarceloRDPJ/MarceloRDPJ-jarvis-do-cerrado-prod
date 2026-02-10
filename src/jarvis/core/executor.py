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
from jarvis.modules.hydration import HydrationModule
# from jarvis.modules.reminders import set_reminder_job # Deprecated in favor of Scheduler
from datetime import datetime

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
            flow = ctx.get("flow")
            text_input = params.get("text", "")

            if flow:
                if flow.get("type") == "hydration_confirm":
                    result = HydrationModule.handle_flow(chat_id, text_input, ctx)
                    if result: return result

                    # Se HydrationModule retornou None, o usuário falou algo fora do contexto (Sim/Não).
                    # Ao invés de travar, tentamos Small Talk ou Chat fallback para manter a fluidez.
                    # Isso permite "Qual a previsão do tempo?" no meio do fluxo sem travar.

                    # Tenta Small Talk
                    st_response = Personality.get_small_talk(text_input)
                    if st_response:
                        return st_response

                    # Se não for small talk, manda fallback genérico (ou deixaria o Brain tratar se tivéssemos acesso)
                    # Como Executor não acessa Brain, usamos fallback da Personalidade.
                    return Personality.get_response("FALLBACK")

            return RemindersFlow.handle_response(chat_id, text_input, ctx)

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
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton

                keyboard = [
                    [
                        InlineKeyboardButton("📅 Meus Lembretes", callback_data="listar lembretes"),
                        InlineKeyboardButton("💧 Status Água", callback_data="status hidratacao")
                    ],
                    [
                        InlineKeyboardButton("🛜 Scan Rede", callback_data="quem ta na rede"),
                        InlineKeyboardButton("🖥️ Sistema", callback_data="status do sistema")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            except ImportError:
                reply_markup = None

            text = (
                "🧠 *Menu de Ajuda do Jarvis do Cerrado*\n\n"
                "_Uai, aqui tá o que eu dou conta de fazer:_\n\n"
                "🌐 *Rede & Dispositivos*\n"
                "• `Quem tá na rede?` - Mostra conexões.\n"
                "• `Mudar o nome do 192.168.1.X para TV` - Renomeia.\n"
                "• `Status da internet` - Teste de velocidade.\n\n"
                "⏰ *Lembretes & Tarefas*\n"
                "• `Me lembre de tomar remédio a cada 8 horas`\n"
                "• `Me lembre no sábado as 14h`\n"
                "• `Me lembre de beber água`\n"
                "• `Listar lembretes` - Ver agenda.\n"
                "• `Cancelar lembrete 1` - Apagar aviso.\n\n"
                "💧 *Saúde & Hidratação*\n"
                "• `Quantas águas eu bebi?` - Progresso.\n"
                "• `Bebi água` - Marca +1.\n\n"
                "🖥️ *Sistema & Segurança*\n"
                "• `Status do sistema` - Diagnóstico.\n\n"
                "_Pode falar do seu jeito que eu entendo. Se não entender, eu pergunto!_"
            )

            return {
                "text": text,
                "reply_markup": reply_markup
            }

        # ---------------- SYSTEM ----------------
        if intent == "system_status":
            return await SystemModule.get_status()

        if intent == "system_reboot":
            return SystemModule.reboot_device()

        if intent == "system_restart_adguard":
            # Hardcoded container name "adguardhome" based on user context
            return SystemModule.restart_container("adguardhome")

        if intent == "menu_system":
            return self._build_menu("System")

        # ---------------- NETWORK ----------------
        if intent == "menu_network":
            return self._build_menu("Network")

        if intent == "network_scan":
            result = await NetworkModule.scan_network()
            # Se for texto simples, envolve com botão de update
            if isinstance(result, str):
                try:
                    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                    keyboard = [[InlineKeyboardButton("🔄 Escanear Novamente", callback_data="quem ta na rede")]]
                    return {"text": result, "reply_markup": InlineKeyboardMarkup(keyboard)}
                except:
                    return result
            return result

        if intent == "network_rename":
            target = params.get("target") # IP
            new_name = params.get("name")

            # Precisamos do MAC para salvar. NetworkModule não expõe fácil o MAC pelo IP ainda.
            # Vamos fazer um scan rápido (cacheado idealmente) ou ler do raw snapshot.
            # raw = await NetworkModule.get_raw_snapshot()
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

        if intent == "menu_reminders":
            return self._build_menu("Reminders", chat_id)

        if intent == "reminder_list":
            text = RemindersFlow.list_reminders(chat_id)
            # Envolve com botões
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = [
                    [
                        InlineKeyboardButton("➕ Novo Lembrete", callback_data="criar lembrete"),
                        InlineKeyboardButton("🗑️ Apagar Lembrete", callback_data="cancelar lembrete")
                    ]
                ]
                return {"text": text, "reply_markup": InlineKeyboardMarkup(keyboard)}
            except:
                return text

        if intent == "reminder_delete":
            # Suporte a params de Rules ('index') ou NLP ('target_id')
            index = params.get("index") or params.get("target_id")
            if index:
                return RemindersFlow.delete_reminder(chat_id, int(index))
            else:
                return "❌ Preciso do número do lembrete. Tenta 'listar lembretes' pra ver os números."

        if intent == "reminder_update":
            index = params.get("index")
            modification = params.get("modification")
            if index:
                return RemindersFlow.update_reminder(chat_id, int(index), modification)
            else:
                 return "❌ Preciso do número do lembrete pra editar."

        # ---------------- FUTUROS ----------------
        if intent == "energy_status":
            return "⚡ Monitoramento de energia em fase de coleta."

        if intent == "hydration_log":
            amount = params.get("amount")
            if amount is None:
                amount = 250 # Default
            return HydrationModule.log_intake(chat_id, amount, manual=True)

        if intent == "hydration_status":
            return HydrationModule.get_status_message(chat_id)

        if intent == "hydration_control":
            return HydrationModule.control_hydration(chat_id, params.get("command", ""))

        if intent == "hydration_update":
            return HydrationModule.update_config(chat_id, params)

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

    # =====================================================
    # HELPER: MENUS DINÂMICOS
    # =====================================================
    def _build_menu(self, menu_type: str, chat_id: int = None) -> Dict[str, Any]:
        try:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        except ImportError:
            return "❌ Erro ao carregar interface gráfica."

        if menu_type == "Network":
            text = "🌐 *Centro de Comando de Rede*\n\n_Monitoramento e controle de tráfego._"
            keyboard = [
                [InlineKeyboardButton("🔍 Scan Total", callback_data="quem ta na rede"), InlineKeyboardButton("🚀 Velocidade", callback_data="status da internet")],
                [InlineKeyboardButton("✏️ Renomear Host", callback_data="ajuda renomear"), InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]
            ]

        elif menu_type == "Reminders":
            text = "⏰ *Gestão Temporal & Tarefas*\n\n_Organização de agenda e hidratação._"
            keyboard = [
                [InlineKeyboardButton("📋 Listar Agenda", callback_data="listar lembretes"), InlineKeyboardButton("➕ Novo Aviso", callback_data="criar lembrete")],
                [InlineKeyboardButton("💧 Status H2O", callback_data="status hidratacao"), InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]
            ]

        elif menu_type == "System":
            text = "🖥️ *Painel de Controle do Sistema*\n\n_Diagnóstico e operações críticas._"
            keyboard = [
                [InlineKeyboardButton("📊 Diagnóstico", callback_data="status do sistema")],
                [InlineKeyboardButton("🛡️ Restart AdGuard", callback_data="reiniciar adguard"), InlineKeyboardButton("🔄 Reboot Host", callback_data="reiniciar sistema")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]
            ]

        else:
            return "Menu desconhecido."

        return {
            "text": text,
            "reply_markup": InlineKeyboardMarkup(keyboard)
        }
