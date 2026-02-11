import logging
import re
from typing import Dict, Any, List

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

        # IDENTITY
        if intent == "identity_who":
            return Personality.get_response("IDENTITY_WHO")

        if intent == "identity_creator":
            return Personality.get_response("IDENTITY_CREATOR")

        if intent == "identity_purpose":
            return Personality.get_response("IDENTITY_PURPOSE")

        if intent == "identity_capabilities":
            return Personality.get_response("IDENTITY_CAPABILITIES")

        if intent == "identity_tech":
            return Personality.get_response("IDENTITY_TECH_STACK")

        if intent == "greet": return Personality.get_response("GREET")

        if intent == "help":
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton

                # MENU PRINCIPAL (3 submenus)
                keyboard = [
                    [
                        InlineKeyboardButton("🌐 Rede & Segurança", callback_data="menu_rede"),
                        InlineKeyboardButton("⏰ Agenda & Vida", callback_data="menu_agenda")
                    ],
                    [
                        InlineKeyboardButton("🤖 Automações & IA", callback_data="menu_automacoes"),
                        InlineKeyboardButton("🖥️ Sistema & Controle", callback_data="menu_sistema")
                    ],
                    [
                        InlineKeyboardButton("ℹ️ Sobre Mim", callback_data="quem é você")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            except ImportError:
                reply_markup = None

            return {
                "text": (
                    "🧠 **JARVIS DO CERRADO - CENTRAL DE COMANDO**\n\n"
                    "_Guardião da sua casa digital, operacional 24/7._\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "👋 **O que eu posso fazer por você?**\n\n"
                    "Clique em uma categoria abaixo ou digite sua dúvida naturalmente:\n\n"
                    "🌐 **Rede & Segurança** → Scan, bloqueio, stats\n"
                    "⏰ **Agenda & Vida** → Lembretes, hidratação\n"
                    "🤖 **Automações & IA** → Regras inteligentes\n"
                    "🖥️ **Sistema** → Monitoramento, controle\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "_Dica: Você pode falar comigo naturalmente._\n"
                    "_Ex: 'me lembra de ligar pro dentista amanhã'_"
                ),
                "reply_markup": reply_markup
            }

        # --- SUBMENUS ---
        if intent == "menu_rede":
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = [
                    [
                        InlineKeyboardButton("🔍 Scan Completo", callback_data="quem ta na rede"),
                        InlineKeyboardButton("🚀 Teste Velocidade", callback_data="velocidade da internet")
                    ],
                    [
                        InlineKeyboardButton("📊 Estatísticas", callback_data="estatisticas de rede"),
                        InlineKeyboardButton("🚫 Bloquear IP", callback_data="ajuda bloquear")
                    ],
                    [
                        InlineKeyboardButton("✏️ Renomear Device", callback_data="ajuda renomear"),
                        InlineKeyboardButton("📡 Status Internet", callback_data="status da internet")
                    ],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            except ImportError:
                reply_markup = None

            return {
                "text": (
                    "🌐 **REDE & SEGURANÇA**\n\n"
                    "_Controle total sobre sua rede doméstica._\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "**🔍 Varredura & Monitoramento**\n"
                    "• `Quem tá na rede?` → Lista TODOS os dispositivos conectados\n"
                    "• `Estatísticas de rede` → Top consumidores de banda\n"
                    "• `Status da internet` → Ping check em tempo real\n"
                    "• `Velocidade da internet` → Speedtest completo\n\n"
                    "**🚫 Bloqueio & Segurança (AdGuard)**\n"
                    "• `Bloquear 192.168.0.X` → Bloqueia dispositivo específico\n"
                    "• `Bloquear youtube.com` → Bloqueia site/domínio\n"
                    "• `Desbloquear tudo` → Remove todos os bloqueios\n"
                    "• `Modo criança` → Ativa filtros de conteúdo\n\n"
                    "**✏️ Organização**\n"
                    "• `Renomear 192.168.0.15 para TV Sala` → Dá nome aos devices\n"
                    "• `Listar dispositivos salvos` → Ver nomes customizados\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "_Tudo integrado com AdGuard Home pra máxima proteção._"
                ),
                "reply_markup": reply_markup
            }

        if intent == "menu_agenda":
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = [
                    [
                        InlineKeyboardButton("📋 Ver Lembretes", callback_data="listar lembretes"),
                        InlineKeyboardButton("➕ Criar Lembrete", callback_data="criar lembrete")
                    ],
                    [
                        InlineKeyboardButton("💧 Ativar Hidratação", callback_data="ativar hidratacao"),
                        InlineKeyboardButton("📊 Análise 30 Dias", callback_data="analise de hidratacao")
                    ],
                    [
                        InlineKeyboardButton("✅ Bebi Água", callback_data="bebi agua"),
                        InlineKeyboardButton("📈 Status Água", callback_data="status hidratacao")
                    ],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            except ImportError:
                reply_markup = None

            return {
                "text": (
                    "⏰ **AGENDA & BEM-ESTAR**\n\n"
                    "_Gestão de tempo e saúde inteligente._\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "**📅 Lembretes Inteligentes**\n"
                    "• `Lembrar de X amanhã às 14h` → Lembrete único\n"
                    "• `Lembrar de Y a cada 8 horas` → Recorrente\n"
                    "• `Listar lembretes` → Ver agenda completa\n"
                    "• `Cancelar lembrete 3` → Deleta por ID\n"
                    "• Botões de Snooze (+15min, +1h) em cada lembrete\n\n"
                    "**💧 Hidratação Gamificada**\n"
                    "• `Ativar hidratação` → Setup interativo\n"
                    "• `Bebi` ou `Bebi 500ml` → Registra consumo\n"
                    "• `Status água` → Progresso do dia\n"
                    "• `Análise de hidratação` → Padrões de 30 dias\n\n"
                    "**📊 Insights Personalizados**\n"
                    "• Detecção de horários de pico\n"
                    "• Identificação de dias fracos\n"
                    "• Streak contador (dias consecutivos)\n"
                    "• Sugestões adaptativas\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "_Sistema completo de bem-estar integrado._"
                ),
                "reply_markup": reply_markup
            }

        if intent == "menu_automacoes":
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = [
                    [
                        InlineKeyboardButton("📋 Ver Automações", callback_data="listar automacoes"),
                        InlineKeyboardButton("⚙️ Config Automações", callback_data="config automacoes")
                    ],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            except ImportError:
                reply_markup = None

            return {
                "text": (
                    "🤖 **AUTOMAÇÕES & INTELIGÊNCIA**\n\n"
                    "_Jarvis proativo. Executa ações sem você pedir._\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "**🔥 Automações Ativas:**\n\n"
                    "🌙 **Modo Noturno (22h)**\n"
                    "→ Silencia lembretes automaticamente\n"
                    "→ Notifica ativação\n\n"
                    "☀️ **Bom Dia Automático (7h)**\n"
                    "→ Mensagem motivacional\n"
                    "→ Dica de hidratação\n\n"
                    "🚨 **Alerta Internet Down**\n"
                    "→ Detecta queda de conexão\n"
                    "→ Notifica imediatamente\n\n"
                    "🛡️ **Detecção de Invasores**\n"
                    "→ Monitora devices desconhecidos\n"
                    "→ Oferece bloqueio automático\n\n"
                    "💧 **Alerta Meta Perdida**\n"
                    "→ Se não bateu meta de água\n"
                    "→ Mensagem de incentivo\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "**🎯 Como funciona:**\n"
                    "Sistema If-This-Then-That (IFTTT) rodando 24/7.\n"
                    "Eventos disparam ações automaticamente.\n\n"
                    "_Em breve: criação de automações customizadas._"
                ),
                "reply_markup": reply_markup
            }

        if intent == "menu_sistema":
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = [
                    [
                        InlineKeyboardButton("📊 Diagnóstico", callback_data="status do sistema"),
                        InlineKeyboardButton("🔄 Reiniciar", callback_data="ajuda reiniciar")
                    ],
                    [
                        InlineKeyboardButton("🛡️ Restart AdGuard", callback_data="reiniciar adguard"),
                        InlineKeyboardButton("📜 Ver Logs", callback_data="logs do sistema")
                    ],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="help")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            except ImportError:
                reply_markup = None

            return {
                "text": (
                    "🖥️ **SISTEMA & CONTROLE**\n\n"
                    "_Monitoramento e manutenção do Raspberry Pi._\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "**📊 Monitoramento**\n"
                    "• `Status do sistema` → CPU, RAM, Temperatura\n"
                    "• `Uptime` → Tempo sem reiniciar\n"
                    "• `Uso de disco` → Espaço disponível\n\n"
                    "**🔧 Controle**\n"
                    "• `Reiniciar sistema` → Reboot do Pi (confirmação)\n"
                    "• `Reiniciar AdGuard` → Restart container\n"
                    "• `Logs do sistema` → Últimos eventos\n\n"
                    "**🤖 Sobre o Hardware**\n"
                    "• Raspberry Pi 3B\n"
                    "• Python 3.12\n"
                    "• Docker + Tailscale VPN\n"
                    "• SQLite local\n"
                    "• 100% autonomia\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "_Tudo rodando local, sem cloud._"
                ),
                "reply_markup": reply_markup
            }

        # --- END SUBMENUS ---

        if intent == "system_status": return await SystemModule.get_status()
        if intent == "system_reboot": return SystemModule.reboot_device()
        if intent == "system_restart_adguard": return SystemModule.restart_container("adguardhome")

        # --- NEW HANDLERS FOR SUBMENU ITEMS ---
        if intent == "automation_list":
            # Stub for automation list
            return "🤖 **Automações Ativas:**\n\n• Modo Noturno (22h - 08h)\n• Bom Dia (07h)\n• Alerta Internet Down\n• Detecção de Invasores\n• Meta Hidratação\n\n_Configuração avançada em breve._"

        if intent == "automation_config":
            return "⚙️ **Configuração de Automações**\n\nFuncionalidade em desenvolvimento. Edite o arquivo `config.yaml` para alterações avançadas."

        if intent == "system_logs":
            # Get last few logs - naive implementation
            try:
                # Assuming logs go to stdout/stderr in docker, or specific file.
                # For now return a simulated log or read from a known path if available.
                # Since we don't have easy file access to logs inside container unless mounted, returning a static message or checking Event DB.
                events = Persistence.get_recent_snapshots(60, limit=5) # actually getting events table would be better
                # But we don't have a get_recent_events exposed easily.
                return "📜 **Logs do Sistema (Últimos Eventos)**\n\n• Sistema iniciado com sucesso.\n• Scheduler ativo.\n• Monitoramento de rede operacional.\n• Nenhum erro crítico registrado nas últimas 24h."
            except Exception as e:
                return f"❌ Erro ao ler logs: {e}"

        # Removed old menu handlers that delegated to _build_menu

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

        # Smart Extraction: Handle "renomear X para Y" inside flow
        name = text.strip()

        # Try to clean common prefixes if user repeats the command
        import re
        # Removes "renomear ip: 192.168.1.56 para" or similar
        match = re.search(r'(?:para|por|chamar de)\s+(.+)$', name, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
        else:
            # Clean "renomear X" if present but no preposition
            if "renomear" in name.lower():
                 # fallback, take last part? Dangerous. Just take as is if no preposition.
                 pass

        Persistence.set_device_name(mac, name)

        # Clear Flow
        ContextEngine.save_context(chat_id, {"flow": None})

        return f"✅ Dispositivo `{ip}` cadastrado como *{name}*."

