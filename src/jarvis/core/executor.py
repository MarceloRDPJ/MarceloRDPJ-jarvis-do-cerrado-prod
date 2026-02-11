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
from jarvis.modules.adguard import AdGuardClient
from datetime import datetime

logger = logging.getLogger("core.executor")


class Executor:
    """
    Executor do Jarvis do Cerrado — EXECUÇÃO CONTROLADA
    """

    SENSITIVE_ACTIONS = {
        "system_reboot",
        "system_shutdown",
        "system_restart_adguard",
        "network_block",
        "network_unblock",
        "network_block_device",
        "network_block_site"
    }

    def __init__(self, application):
        self.app = application
        Persistence.init_db()
        self.pending_actions: Dict[int, Dict[str, Any]] = {}
        logger.info("Executor inicializado com sucesso.")

    async def execute(self, intent_data: Dict[str, Any], chat_id: int) -> str:
        if not isinstance(intent_data, dict):
            return "❌ Comando inválido."

        intent: str = intent_data.get("intent")
        action: str = intent_data.get("action", "default")
        params: Dict[str, Any] = intent_data.get("params", {})
        requires_confirmation: bool = intent_data.get("requires_confirmation", False)

        logger.info(f"Executor → intent={intent} | action={action}")

        # Log & Context
        try:
            Persistence.log_event(Event(type=f"{intent}.{action}", source="executor", payload=intent_data))
            ContextEngine.save_context(chat_id, intent_data)
        except Exception:
            logger.exception("Erro ao registrar evento/contexto")

        # Confirmation
        if intent == "action_confirm": return await self._confirm_action(chat_id)
        if intent == "action_cancel": return self._cancel_action(chat_id)

        # Enforce Confirmation for Sensitive Actions
        if intent in self.SENSITIVE_ACTIONS:
            requires_confirmation = True

        if requires_confirmation:
            self.pending_actions[chat_id] = intent_data
            return "⚠️ *Ação sensível detectada.* Digite **confirmar** ou **cancelar**."

        return await self._execute_intent(intent, action, params, chat_id)

    async def _execute_intent(self, intent: str, action: str, params: Dict[str, Any], chat_id: int) -> str:
        # ---------------- NETWORK SCAN (UX Aprimorada) ----------------
        if intent == "network_scan":
            # 1. Send Initial Status Message
            status_msg = await self.app.bot.send_message(
                chat_id=chat_id,
                text="⏳ Iniciando varredura profunda da rede...",
                parse_mode="Markdown"
            )

            # 2. Callback for Updates
            last_text = ""
            async def update_status(text):
                nonlocal last_text
                if text != last_text:
                    try:
                        await self.app.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_msg.message_id,
                            text=text,
                            parse_mode="Markdown"
                        )
                        last_text = text
                    except Exception as e:
                        logger.warning(f"Failed to update status: {e}")

            # 3. Run Deep Scan
            try:
                devices = await NetworkModule.scan_network_deep(status_callback=update_status, app=self.app)

                # 4. Format Final Report
                if not devices:
                    final_text = "⚠️ Nenhum dispositivo encontrado."
                else:
                    final_text = f"🕵️‍♂️ *Relatório de Rede ({len(devices)} dispositivos):*\n\n"

                    for d in devices:
                        ip = d['ip']
                        mac = d['mac']
                        vendor = d['vendor']
                        name = d['custom_name']
                        hostname = d['hostname']
                        guess = d['guessed_type']

                        # Icon Logic
                        icon = "🖥️"
                        desc = vendor

                        if "Apple" in guess: icon = "🍎"
                        elif "Linux" in guess: icon = "🐧"
                        elif "Windows" in guess: icon = "🪟"
                        elif "IoT" in guess: icon = "🔌"
                        elif "Raspberry" in guess: icon = "🍓"

                        # Name Priority: Custom > Hostname > Vendor
                        display_name = name if name else (hostname if hostname else vendor)

                        # Extra info line
                        extra = ""
                        if guess != "Dispositivo Desconhecido":
                            extra = f" _({guess})_"
                        elif hostname:
                            extra = f" _(Host: {hostname})_"

                        final_text += f"{icon} `{ip}` — *{display_name}*{extra}\n"

                # 5. Final Update (overwrite status message)
                try:
                    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                    keyboard = [[InlineKeyboardButton("🔄 Escanear Novamente", callback_data="quem ta na rede")]]
                    await self.app.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                        text=final_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode="Markdown"
                    )
                    return None # Already sent response via edit
                except:
                    return final_text

            except Exception as e:
                logger.exception("Deep scan failed")
                return f"❌ Erro durante a varredura: {e}"

        # ---------------- FLOW INPUT ----------------
        if intent == "flow_input":
            ctx = ContextEngine.get_context(chat_id)
            flow = ctx.get("flow")
            text_input = params.get("text", "")
            if flow:
                # Trata fluxos de rede (Cadastro)
                if flow.get("type") == "network_register":
                    result = await self._handle_network_registration(chat_id, text_input, ctx)
                    if result: return result

                # Trata fluxos de hidratação (Setup ou Confirm)
                if flow.get("type") in ["hydration_confirm", "hydration_setup"]:
                    result = HydrationModule.handle_flow(chat_id, text_input, ctx)
                    if result: return result
                    st_response = Personality.get_small_talk(text_input)
                    if st_response: return st_response
                    return Personality.get_response("FALLBACK")
            return RemindersFlow.handle_response(chat_id, text_input, ctx)

        # ---------------- STANDARD INTENTS ----------------
        if intent == "chat": return params.get("response", Personality.get_response("FALLBACK"))
        if intent == "small_talk": return Personality.get_small_talk(params.get("text", ""))
        if intent == "identity_who": return Personality.get_response("IDENTITY_WHO")
        if intent == "identity_capabilities": return Personality.get_response("IDENTITY_CAPABILITIES")
        if intent == "greet": return Personality.get_response("GREET")

        if intent == "help":
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = [
                    [
                        InlineKeyboardButton("🛜 Scan Rede", callback_data="quem ta na rede"),
                        InlineKeyboardButton("🚀 Velocidade", callback_data="velocidade da internet")
                    ],
                    [
                        InlineKeyboardButton("💧 Ativar Hidratação", callback_data="ativar hidratacao"),
                        InlineKeyboardButton("📊 Status Água", callback_data="status hidratacao")
                    ],
                    [
                        InlineKeyboardButton("📅 Ver Agenda", callback_data="listar lembretes"),
                        InlineKeyboardButton("🖥️ Status Sistema", callback_data="status do sistema")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            except ImportError: reply_markup = None

            return {
                "text": (
                    "🧠 *Menu de Comando — Jarvis do Cerrado*\n\n"
                    "_Opa! Tudo que eu posso fazer tá aqui, ó:_\n\n"
                    "🌐 *Rede & Conexão*\n"
                    "• `Quem tá na rede?` - Lista dispositivos.\n"
                    "• `Status da internet` - Checa se tá tudo on.\n"
                    "• `Velocidade da internet` - Teste rápido.\n"
                    "• `Renomear 192.168.1.X para TV` - Organiza a casa.\n\n"
                    "⏰ *Agenda & Lembretes*\n"
                    "• `Lembrar de tomar remédio a cada 8h`\n"
                    "• `Lembrar de reunião amanhã às 14h`\n"
                    "• `Listar lembretes` - Ver o que tá pendente.\n\n"
                    "💧 *Hidratação Inteligente*\n"
                    "• `Ativar Hidratação` - Começa o monitoramento.\n"
                    "• `Bebi água` - Registra um copo.\n"
                    "• `Status água` - Vê sua meta do dia.\n\n"
                    "🖥️ *Sistema*\n"
                    "• `Status do sistema` - CPU, RAM e Temperatura.\n\n"
                    "_Se precisar de algo mais específico, é só pedir com jeitinho._"
                ),
                "reply_markup": reply_markup
            }

        if intent == "system_status": return await SystemModule.get_status()
        if intent == "system_reboot": return SystemModule.reboot_device()
        if intent == "system_restart_adguard": return SystemModule.restart_container("adguardhome")
        if intent == "menu_system": return self._build_menu("System")
        if intent == "menu_network": return self._build_menu("Network")

        if intent == "network_speed":
            await self.app.bot.send_message(chat_id=chat_id, text="🚀 Iniciando teste de velocidade... segura a onda que demora uns segundos.")
            return await NetworkModule.run_speedtest()

        if intent == "network_status": return await NetworkModule.check_ping()

        if intent == "network_rename":
            target = params.get("target")
            new_name = params.get("name")
            mac = await NetworkModule.resolve_mac_by_ip(target)
            if mac and new_name:
                Persistence.set_device_name(mac, new_name)
                return f"✅ Dispositivo {target} agora é conhecido como *{new_name}*."
            elif not mac: return f"❌ Não encontrei o IP {target} na rede agora."
            else: return "❌ Preciso do IP e do novo nome. Ex: mudar nome do 192.168.1.5 para TV Sala"

        if intent == "network_block_device":
            ip = params.get("ip") or params.get("target")
            if not ip:
                return "❌ Preciso do IP. Ex: bloquear 192.168.0.15"

            result = await AdGuardClient.block_client(ip)
            if result["success"]:
                return f"🚫 Dispositivo {ip} bloqueado no AdGuard."
            else:
                return f"❌ Erro ao bloquear: {result['message']}"

        if intent == "network_block_site":
            site = params.get("site") or params.get("domain")
            if not site:
                return "❌ Qual site? Ex: bloquear youtube.com"

            result = await AdGuardClient.block_client(site, name=f"Bloqueio {site}")
            if result["success"]:
                return f"🚫 Site {site} bloqueado."
            else:
                return f"❌ Erro: {result['message']}"

        if intent == "network_stats":
            stats = await AdGuardClient.get_stats()
            top = await AdGuardClient.get_top_clients(limit=5)

            msg = f"📊 **Estatísticas de Rede**\n\n"
            msg += f"DNS Queries: {stats.get('num_dns_queries', 0)}\n"
            msg += f"Bloqueados: {stats.get('num_blocked_filtering', 0)}\n\n"
            msg += f"**Top 5 Consumidores:**\n"

            for client in top:
                msg += f"• {client['name'] or client['ip']}: {client['queries']} queries\n"

            return msg

        if intent == "context_query":
            try: return f"📊 Resultado técnico:\n```{ContextReader.handle(params)}```"
            except: return "❌ Erro ao analisar histórico."

        if intent == "reminder_set":
            if action == "create_request": return RemindersFlow.start_flow(chat_id, params)
            return "Modo de criação direta descontinuado. Use fluxo interativo."

        if intent == "menu_reminders": return self._build_menu("Reminders", chat_id)

        if intent == "reminder_list":
            text = RemindersFlow.list_reminders(chat_id)
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = [[InlineKeyboardButton("➕ Novo Lembrete", callback_data="criar lembrete"), InlineKeyboardButton("🗑️ Apagar Lembrete", callback_data="cancelar lembrete")]]
                return {"text": text, "reply_markup": InlineKeyboardMarkup(keyboard)}
            except: return text

        if intent == "reminder_delete":
            index = params.get("index") or params.get("target_id")
            if index: return RemindersFlow.delete_reminder(chat_id, int(index))
            else: return "❌ Preciso do número do lembrete. Tenta 'listar lembretes' pra ver os números."

        if intent == "reminder_update":
            index = params.get("index")
            modification = params.get("modification")
            if index: return RemindersFlow.update_reminder(chat_id, int(index), modification)
            else: return "❌ Preciso do número do lembrete pra editar."

        if intent == "energy_status": return "⚡ Monitoramento de energia em fase de coleta."

        if intent in ["hydration_log", "hydration_log_explicit"]:
            amount = params.get("amount")
            return HydrationModule.log_intake(chat_id, amount, manual=True, explicit=True)

        if intent == "hydration_log_implicit":
            return HydrationModule.log_intake(chat_id, None, manual=True, explicit=False)

        if intent == "hydration_analytics":
            return HydrationModule.get_analytics(chat_id)

        if intent == "hydration_activate": return HydrationModule.activate_flow(chat_id)
        if intent == "hydration_status": return HydrationModule.get_status_message(chat_id)
        if intent == "hydration_control": return HydrationModule.control_hydration(chat_id, params.get("command", ""))
        if intent == "hydration_update": return HydrationModule.update_config(chat_id, params)
        if intent == "automation_create": return "🤖 Automação registrada. Vou observar."

        logger.warning(f"Intent não tratada pelo Executor: {intent}")
        return "🤖 Ainda não sei executar isso… mas já anotei."

    async def _confirm_action(self, chat_id: int) -> str:
        pending = self.pending_actions.pop(chat_id, None)
        if not pending: return "⚠️ Nenhuma ação pendente para confirmar."
        logger.info(f"Ação confirmada pelo usuário: {pending}")
        return await self._execute_intent(pending.get("intent"), pending.get("action", "default"), pending.get("params", {}), chat_id)

    def _cancel_action(self, chat_id: int) -> str:
        if chat_id in self.pending_actions:
            self.pending_actions.pop(chat_id)
            return "🛑 Ação cancelada com sucesso."
        return "⚠️ Nenhuma ação pendente para cancelar."

    async def handle_network_callback(self, chat_id: int, data: str, query):
        """
        Trata callbacks 'net_xxx' vindos de automações.
        """
        parts = data.split("_")
        action = parts[1] # reg, block, ignore

        if action == "ignore":
            await query.edit_message_text("👁️ Dispositivo ignorado.")
            return

        if action == "block":
            ip = parts[2]
            # Calls internal intent
            msg = await self._execute_intent("network_block_device", "block", {"ip": ip}, chat_id)
            await query.edit_message_text(msg)
            return

        if action == "reg":
            # net_reg_{ip}_{mac}
            ip = parts[2]
            mac = parts[3] if len(parts) > 3 else None

            if not mac:
                 # Try resolve if missing (legacy compat)
                 mac = await NetworkModule.resolve_mac_by_ip(ip)

            if not mac:
                 await query.edit_message_text("❌ Não consegui identificar o MAC address para cadastro.")
                 return

            # Start Flow
            ContextEngine.save_context(chat_id, {
                "flow": {
                    "type": "network_register",
                    "step": "ask_name",
                    "data": {"ip": ip, "mac": mac}
                }
            })

            await query.edit_message_text(f"📝 *Cadastro de Dispositivo*\nIP: `{ip}`\nMAC: `{mac}`\n\nQual nome você quer dar para ele?")
            return

    async def _handle_network_registration(self, chat_id: int, text: str, ctx: Dict) -> str:
        flow = ctx.get("flow")
        data = flow.get("data")
        mac = data.get("mac")
        ip = data.get("ip")

        # Save Name
        name = text.strip()
        Persistence.set_device_name(mac, name)

        # Clear Flow
        ContextEngine.save_context(chat_id, {"flow": None})

        return f"✅ Dispositivo `{ip}` cadastrado como *{name}*."

    def _build_menu(self, menu_type: str, chat_id: int = None) -> Dict[str, Any]:
        try: from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        except ImportError: return "❌ Erro ao carregar interface gráfica."

        if menu_type == "Network":
            text = "🌐 *Centro de Comando de Rede*\n\n_Monitoramento e controle de tráfego._"
            keyboard = [[InlineKeyboardButton("🔍 Scan Total", callback_data="quem ta na rede"), InlineKeyboardButton("🚀 Velocidade", callback_data="velocidade da internet")], [InlineKeyboardButton("✏️ Renomear Host", callback_data="ajuda renomear"), InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]]
        elif menu_type == "Reminders":
            text = "⏰ *Gestão Temporal & Tarefas*\n\n_Organização de agenda e hidratação._"
            keyboard = [[InlineKeyboardButton("📋 Listar Agenda", callback_data="listar lembretes"), InlineKeyboardButton("➕ Novo Aviso", callback_data="criar lembrete")], [InlineKeyboardButton("💧 Status H2O", callback_data="status hidratacao"), InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]]
        elif menu_type == "System":
            text = "🖥️ *Painel de Controle do Sistema*\n\n_Diagnóstico e operações críticas._"
            keyboard = [[InlineKeyboardButton("📊 Diagnóstico", callback_data="status do sistema")], [InlineKeyboardButton("🛡️ Restart AdGuard", callback_data="reiniciar adguard"), InlineKeyboardButton("🔄 Reboot Host", callback_data="reiniciar sistema")], [InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]]
        else: return "Menu desconhecido."

        return {"text": text, "reply_markup": InlineKeyboardMarkup(keyboard)}
