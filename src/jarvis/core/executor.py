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
from jarvis.config import Config
import os
import asyncio
import time

logger = logging.getLogger("core.executor")


class Executor:
    """
    Executor do ROD do Cerrado — EXECUÇÃO CONTROLADA
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
        # ===== VALIDAÇÃO DE SEGURANÇA - ADICIONAR AQUI =====

        # Valida que apenas usuário autorizado pode executar comandos
        if chat_id != Config.ALLOWED_USER_ID:
            logger.warning(f"🚨 Tentativa de acesso não autorizado: chat_id={chat_id}")
            return "🚫 Acesso negado. Você não está autorizado a usar este bot."

        # ===== FIM DA VALIDAÇÃO =====

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
        # ---------------- COMMAND LIST (NEW) ----------------
        if intent == "command_list":
            return (
                "📜 **MANUAL DE COMANDOS — ROD DO CERRADO**\n"
                "_Lista completa de tudo que eu entendo e executo._\n\n"

                "🌐 **REDE & SEGURANÇA**\n"
                "• `quem ta na rede` → Varredura de dispositivos conectados.\n"
                "• `velocidade da internet` → Teste de velocidade (Speedtest).\n"
                "• `status da internet` → Teste de latência (Ping).\n"
                "• `estatisticas de rede` → Dados do AdGuard (queries, blocks).\n"
                "• `renomear [IP] para [NOME]` → Dar apelido a um dispositivo.\n"
                "• `bloquear [IP]` → Bloquear acesso à internet do dispositivo.\n"
                "• `bloquear [SITE]` → Bloquear domínio (ex: youtube.com).\n\n"

                "⏰ **AGENDA & LEMBRETES**\n"
                "• `lembrar de [TEXTO] [TEMPO]` → Criar lembrete.\n"
                "   _Ex: 'lembrar de tirar o lixo as 18h'_\n"
                "   _Ex: 'lembrar de tomar remedio a cada 8h'_\n"
                "• `listar lembretes` → Ver agenda ativa.\n"
                "• `cancelar lembrete [ID]` → Apagar pelo número.\n"
                "• `editar lembrete [ID] [NOVO TEXTO/HORA]` → Alterar.\n\n"

                "💧 **HIDRATAÇÃO**\n"
                "• `ativar hidratação` → Configuração inicial guiada.\n"
                "• `bebi` ou `tomei agua` → Registrar consumo.\n"
                "• `status hidratação` → Meta vs Consumido.\n"
                "• `analise de hidratação` → Relatório de 30 dias.\n"
                "• `pausar/retomar hidratação` → Controle do fluxo.\n"
                "• `mudar meta para [X]` → Ajustar meta diária.\n\n"

                "🖥️ **SISTEMA**\n"
                "• `status do sistema` → CPU, RAM, Temp, Uptime.\n"
                "• `logs do sistema` → Últimos eventos registrados.\n"
                "• `reiniciar sistema` → Reboot do Raspberry Pi.\n"
                "• `reiniciar adguard` → Restart do container DNS.\n\n"

                "🤖 **AUTOMAÇÕES & OUTROS**\n"
                "• `listar automacoes` → Ver regras ativas.\n"
                "• `config automacoes` → Informações sobre config.\n"
                "• `quem é você` → Identidade.\n"
                "• `ajuda` → Menu interativo principal.\n"
            )

        # ---------------- NETWORK SCAN (UX Aprimorada) ----------------
        if intent == "network_scan":
            # 1. Send Initial Status Message
            status_msg = await self.app.bot.send_message(
                chat_id=chat_id,
                text="⏳ Iniciando varredura profunda da rede...",
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
                        )
                        last_text = text
                    except Exception as e:
                        logger.warning(f"Failed to update status: {e}")

            # 3. Run Deep Scan
            try:
                devices = await NetworkModule.scan_network_deep(status_callback=update_status)

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

                if flow.get("type") == "reminder_reschedule":
                    return RemindersFlow.handle_reschedule_response(chat_id, text_input, ctx)
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
                        InlineKeyboardButton("⚙️ Automações", callback_data="menu_automacoes"),
                        InlineKeyboardButton("🖥️ Sistema & Controle", callback_data="menu_sistema")
                    ],
                    [
                        InlineKeyboardButton("🧾 Contas & Faturas", callback_data="menu_contas")
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
                    "🧠 **ROD DO CERRADO - CENTRAL DE COMANDO**\n\n"
                    "_Guardião da sua casa digital, operacional 24/7._\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "👋 **O que eu posso fazer por você?**\n\n"
                    "Clique em uma categoria abaixo ou digite sua dúvida naturalmente:\n\n"
                    "🌐 **Rede & Segurança** → Scan, bloqueio, stats\n"
                    "⏰ **Agenda & Vida** → Lembretes, hidratação\n"
                    "⚙️ **Automações** → Regras locais e alertas\n"
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
                    "• `Estatísticas de rede` → Consultas e bloqueios do AdGuard\n"
                    "• `Status da internet` → Ping check em tempo real\n"
                    "• `Velocidade da internet` → Speedtest completo\n\n"
                    "**🚫 Bloqueio & Segurança (AdGuard)**\n"
                    "• `Bloquear 192.168.0.X` → Bloqueia dispositivo específico\n"
                    "• `Bloquear youtube.com` → Bloqueia site/domínio\n"
                    "• Bloqueios alteram regras do AdGuard e pedem confirmação\n\n"
                    "**✏️ Organização**\n"
                    "• `Renomear 192.168.0.15 para TV Sala` → Dá nome aos devices\n"
                    "• Nomes cadastrados aparecem nas próximas varreduras\n\n"
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
                    "• Resumo baseado no histórico salvo\n\n"
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
                    "🤖 Automações & Inteligência\n\n"
                    "Regras locais verificáveis. Sem fingir integração que não existe.\n\n"
                    "Toque em Ver Automações para eu listar o que o motor carregou de verdade.\n\n"
                    "Como funciona:\n"
                    "Sistema local de regras simples. Algumas ações dependem de serviços configurados.\n\n"
                    "Criação/edição pelo Telegram ainda não está pronta."
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
                    [InlineKeyboardButton("📱 Status do Poco", callback_data="status do poco")],
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

        if intent == "menu_contas":
            try:
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = [
                    [InlineKeyboardButton("💧 Saneago — Casa", callback_data="conta de agua casa")],
                    [InlineKeyboardButton("⚡ Equatorial — Casa", callback_data="conta de luz casa")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="help")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            except ImportError:
                reply_markup = None
            return {
                "text": (
                    "🧾 CONTAS & FATURAS\n\n"
                    "As consultas são executadas no Poco e os acessos ficam criptografados "
                    "no Android Keystore. Diga a concessionária e o imóvel, por exemplo:\n"
                    "conta de água kitnet 01 ou conta de luz restaurante.\n\n"
                    "Se o portal exigir CAPTCHA ou confirmação humana, eu aviso claramente."
                ),
                "reply_markup": reply_markup,
            }

        # --- END SUBMENUS ---

        if intent == "system_status": return await SystemModule.get_status()
        if intent == "poco_status":
            return await self._poco_status()
        if intent == "poco_network_check":
            return await self._poco_network_check()
        if intent == "saneago_bills":
            return await self._poco_saneago_bills(params)
        if intent == "equatorial_bills":
            return await self._poco_equatorial_bills(params)
        if intent == "fan_control":
            return await self._handle_fan_control(params.get("text", ""), self.app)
        if intent == "system_reboot": return SystemModule.reboot_device()
        if intent == "system_restart_adguard": return SystemModule.restart_container("adguardhome")

        # --- NEW HANDLERS FOR SUBMENU ITEMS ---
        if intent == "automation_list":
            automation = getattr(self.app, "bot_data", {}).get("automation") if self.app else None
            if not automation:
                return "🤖 Automações\n\nMotor de automações não está disponível agora. Nenhuma automação confirmada."
            rules = getattr(automation, "rules", []) or []
            if not rules:
                return "🤖 Automações\n\nNenhuma regra carregada."
            lines = []
            for rule in rules:
                status = "ativa" if rule.get("enabled") else "pausada"
                trigger = rule.get("trigger", {})
                if trigger.get("type") == "time":
                    trigger_desc = f"horário {trigger.get('time')}"
                else:
                    trigger_desc = f"evento {trigger.get('event_type', 'desconhecido')}"
                lines.append(f"• {rule.get('name', rule.get('id'))}: {status} ({trigger_desc})")
            return "🤖 Automações carregadas\n\n" + "\n".join(lines) + "\n\nAções dependentes de integrações externas só executam se o serviço estiver configurado."

        if intent == "automation_config":
            return "⚙️ Configuração de Automações\n\nCriação/edição pelo Telegram ainda não está implementada. Hoje eu apenas listo e executo as regras locais carregadas no código/configuração."

        if intent == "system_logs":
            try:
                events = Persistence.get_recent_events(limit=5)
                if events:
                    lines = [f"• `{e['type']}` de `{e['source']}` em {e['timestamp'][:19]}" for e in events]
                    return "📜 **Logs do Sistema (Últimos Eventos)**\n\n" + "\n".join(lines)

                snapshots = Persistence.get_recent_snapshots(1440, limit=5)
                if snapshots:
                    lines = [f"• Snapshot {s['timestamp'][:19]}" for s in snapshots]
                    return "📜 **Snapshots Recentes (24h)**\n\n" + "\n".join(lines)

                return "📜 **Logs do Sistema**\n\nNenhum evento ou snapshot registrado."
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

            result = await AdGuardClient.block_domain(site, name=f"Bloqueio {site}")
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

        # Wake-on-LAN
        if intent == "wake_pc":
            # Confirmação para ação sensível
            if not params.get("confirmed"):
                self.pending_actions[chat_id] = {
                    "intent": "wake_pc",
                    "params": {"confirmed": True}
                }
                return (
                    "🖥️ *Wake-on-LAN*\n\n"
                    "Vou enviar pacote mágico para ligar o PC.\n\n"
                    "MAC configurado: `{}`\n\n"
                    "Confirma? Digite *confirmar* ou *cancelar*."
                ).format(Config.PC_MAC or "NÃO CONFIGURADO")

            # Executa Wake-on-LAN
            try:
                result = await NetworkModule.wake_on_lan(Config.PC_MAC)
                if not result.get("success"):
                    return f"❌ Erro ao enviar pacote WOL: {result.get('message', 'falha desconhecida')}"

                return (
                    "🖥️ *Pacote WOL Enviado!*\n\n"
                    "Pacote mágico enviado para: `{}`\n\n"
                    "O PC deve ligar em alguns segundos.\n"
                    "Aguarde 30-60 segundos e verifique se está online."
                ).format(Config.PC_MAC)

            except Exception as e:
                logger.error(f"Erro ao executar Wake-on-LAN: {e}")
                return f"❌ Erro ao enviar pacote WOL: {str(e)}"

        # Status do PC
        if intent == "pc_status":
            # Tenta pingar o PC (assumindo que IP está configurado)
            pc_ip = os.getenv("PC_IP", "192.168.0.100")  # IP do PC
            online = await NetworkModule.check_device_online(pc_ip)

            if online:
                return f"🟢 PC está ONLINE ({pc_ip})"
            else:
                return f"🔴 PC está OFFLINE ou não respondendo ({pc_ip})"

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
                keyboard = [[InlineKeyboardButton("➕ Novo Lembrete", callback_data="criar lembrete"), InlineKeyboardButton("🗑️ Apagar Lembrete", callback_data="reminder_delete_menu")]]
                return {"text": text, "reply_markup": InlineKeyboardMarkup(keyboard)}
            except: return text

        if intent == "reminder_today":
            return RemindersFlow.list_today(chat_id)

        if intent == "reminder_overdue":
            return RemindersFlow.list_overdue(chat_id)

        if intent == "reminder_delete":
            index = params.get("index") or params.get("target_id")
            if index: return RemindersFlow.delete_reminder(chat_id, int(index))
            else: return "❌ Preciso do número do lembrete. Tenta 'listar lembretes' pra ver os números."

        if intent == "reminder_update":
            index = params.get("index")
            modification = params.get("modification")
            if index: return RemindersFlow.update_reminder(chat_id, int(index), modification)
            else:
                reminders = RemindersFlow.list_reminders(chat_id)
                return (
                    f"Pra editar eu preciso do número do lembrete.\n\n"
                    f"{reminders}\n"
                    f"Exemplo: `editar lembrete 1 para hoje às 20h`"
                )

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
        if intent == "automation_create": return "🤖 Ainda não consigo criar automações novas pelo chat com segurança. Posso listar as regras carregadas e executar as existentes."

        if intent == "token_usage":
            return await Executor._get_token_usage_report()

        if intent == "daily_report":
            return await Executor._get_daily_report()

        if intent == "unknown_queries":
            return Executor._get_unknown_queries()

        logger.warning(f"Intent não tratada pelo Executor: {intent}")
        return "🤖 Ainda não sei executar isso… mas já anotei."

    @staticmethod
    async def _handle_fan_control(text: str, app) -> str:
        fan_service = app.bot_data.get("fan_service")
        if not fan_service:
            return "❌ Serviço de controle da ventoinha (FanControlService) não está inicializado."

        t = text.lower()
        if "ligar" in t:
            if fan_service.fan:
                fan_service.fan.on()
                fan_service.manual_override = True
                return "🌬️ Ventoinha **ligada** manualmente. O controle automático está pausado. Use 'voltar pro auto' para reativar."
            return "❌ Fan hardware não disponível."
        elif "desligar" in t:
            if fan_service.fan:
                fan_service.fan.off()
                fan_service.manual_override = True
                return "🛑 Ventoinha **desligada** manualmente. O controle automático está pausado. Use 'voltar pro auto' para reativar."
            return "❌ Fan hardware não disponível."
        elif "auto" in t:
            fan_service.manual_override = False
            return "✅ Controle automático da ventoinha reativado."
        else:
            state = "LIGADA" if fan_service.fan and fan_service.fan.is_active else "DESLIGADA"
            override = " (Manual Override)" if fan_service.manual_override else " (Automático)"
            return (
                f"🌬️ *Status da Ventoinha*\n\n"
                f"Estado Atual: **{state}{override}**\n"
                f"GPIO Pin: `{fan_service.pin}`\n"
                f"Liga acima de: `{fan_service.threshold_on}°C`\n"
                f"Desliga abaixo de: `{fan_service.threshold_off}°C`"
            )

    @staticmethod
    async def _get_token_usage_report() -> str:
        from jarvis.database.persistence import Persistence
        today = Persistence.get_token_usage_today()
        all_time = Persistence.get_token_usage_all_time()

        msg = "📊 *Consumo de IA*\n\n"
        msg += f"*Hoje:*\n"
        msg += f"• Chamadas: {today['calls']}\n"
        msg += f"• Tokens: {today['total']} ({today['prompt']} in / {today['completion']} out)\n"
        msg += f"• Custo: ${today['cost']:.6f}\n\n"
        msg += f"*Total (todo histórico):*\n"
        msg += f"• Chamadas: {all_time['calls']}\n"
        msg += f"• Tokens: {all_time['total']}\n"
        msg += f"• Custo: ${all_time['cost']:.6f}\n\n"

        if today['calls'] == 0:
            msg += "_Nenhuma chamada de API hoje. O ROD resolveu tudo localmente/gratuito._ 🤖"
        else:
            msg += f"_Custo médio por chamada: ${today['cost']/max(today['calls'],1):.8f}_"

        return msg

    @staticmethod
    async def _get_daily_report() -> str:
        from jarvis.database.persistence import Persistence
        from jarvis.modules.network import NetworkModule
        from jarvis.modules.system import SystemModule
        import os

        # Token usage
        tokens = Persistence.get_token_usage_today()
        unknown = Persistence.get_unknown_queries_today()
        errors = Persistence.get_api_errors_today()

        # System status
        try:
            raw = await SystemModule.get_raw_status()
            temp = f"{raw['temperature_c']}C" if raw.get('temperature_c') else "N/A"
            uptime = str(__import__('datetime').timedelta(seconds=raw['uptime_seconds']))
            sys_info = f"CPU: {raw['cpu_percent']}% | RAM: {raw['memory']['percent']}% | Temp: {temp}"
        except:
            sys_info = "N/A"

        # Internet
        try:
            ping = await NetworkModule.get_ping_metrics()
            net = "Online" if ping.get('success') else "Offline"
            lat = ping.get('latency_ms', 'N/A')
            net_info = f"{net} ({lat}ms)"
        except:
            net_info = "N/A"

        msg = "📋 *Relatório Diário — ROD do Cerrado*\n\n"
        msg += f"🖥️ *Sistema*\n{sys_info}\nUptime: {uptime}\n\n"
        msg += f"🌐 *Internet*\n{net_info}\n\n"
        msg += f"🤖 *IA Local / Gratuita*\n"
        msg += f"• {tokens['calls']} chamadas · {tokens['total']} tokens\n"
        msg += f"• Custo: ${tokens['cost']:.6f}\n\n"

        if unknown:
            msg += f"❓ *Consultas não reconhecidas:* {len(unknown)}\n"
            for q in unknown[:5]:
                msg += f"• _{q['query'][:50]}_\n"
            msg += "\n"

        if errors:
            msg += f"⚠️ *Erros de API:* {len(errors)}\n\n"
        else:
            msg += "✅ *Nenhum erro de API hoje.*\n\n"

        msg += "_Relatório 100% local — zero tokens gastos para gerar isso._"
        return msg

    @staticmethod
    def _get_unknown_queries() -> str:
        from jarvis.database.persistence import Persistence
        queries = Persistence.get_unknown_queries_today()
        total = Persistence.get_unknown_queries_count(days=30)

        if not queries:
            return "❓ Nenhuma consulta desconhecida hoje. Tô entendendo tudo! 🤖"

        msg = f"📝 *Consultas não reconhecidas (hoje: {len(queries)}, 30d: {total})*\n\n"
        for q in queries:
            msg += f"• ❓ {q['query'][:60]}\n"

        msg += "\n_Essas queries são registradas para eu aprender e melhorar._"
        return msg

    async def _confirm_action(self, chat_id: int) -> str:
        pending = self.pending_actions.pop(chat_id, None)
        if not pending: return "⚠️ Nenhuma ação pendente para confirmar."
        logger.info(f"Ação confirmada pelo usuário: {pending}")
        return await self._execute_intent(pending.get("intent"), pending.get("action", "default"), pending.get("params", {}), chat_id)

    @staticmethod
    async def _run_poco_job(action: str, timeout_seconds: int = 70, params: dict | None = None):
        if not Config.POCO_NODE_ENABLED:
            return None, "O nó Poco está desativado na configuração."
        from jarvis.api.app import get_poco_service

        service = get_poco_service()
        if not service.status().get("online"):
            return None, "O Poco está offline ou sem heartbeat recente."
        job = service.enqueue(action, params=params or {}, ttl_seconds=timeout_seconds + 30)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            current = service.get_job(job.job_id)
            if current and current.status == "completed":
                return current.result or {}, None
            if current and current.status in {"failed", "expired"}:
                return None, current.error or "A tarefa expirou antes de concluir."
            await asyncio.sleep(2)
        return None, "O Poco não concluiu a tarefa dentro do tempo esperado."

    async def _poco_bill_cache_note(self, provider: str, property_key: str) -> str:
        """Última leitura confirmada guardada no Poco.

        Vale como consolo quando a consulta ao vivo falha, mas só pode aparecer
        com data explícita. Cache apresentado como medição atual seria mentira.
        """
        result, error = await self._run_poco_job(
            "read_bill_cache", 30, {"provider": provider, "property": property_key}
        )
        if error or not result:
            return ""
        age = result.get("cache_age_seconds")
        if not isinstance(age, (int, float)) or age < 0:
            when = "em data desconhecida"
        elif age < 3600:
            when = f"há {int(age // 60)} min"
        elif age < 86400:
            when = f"há {int(age // 3600)} h"
        else:
            when = f"há {int(age // 86400)} dia(s)"
        amount = result.get("amount", "indisponível")
        due = result.get("due_date", "indisponível")
        return (
            f"\n\nÚltima leitura confirmada ({when}): fatura {amount}, "
            f"vencimento {due}. Isso é cache do Poco, não a consulta de agora."
        )

    async def _poco_status(self) -> str:
        from jarvis.api.app import get_poco_service

        status = get_poco_service().status()
        heartbeat = status.get("heartbeat") or {}
        if not status.get("online"):
            return "Poco: offline ou sem sinal recente. O ROD no Pi continua funcionando."
        battery = heartbeat.get("battery_level")
        temperature = heartbeat.get("battery_temperature_c")
        wifi = "conectado" if heartbeat.get("wifi_connected") else "desconectado"
        return f"Poco: online. Bateria: {battery:.0f}%, Temp: {temperature:.1f} °C, Wi-Fi: {wifi}."

    async def _poco_network_check(self) -> str:
        result, error = await self._run_poco_job("network_check", 45)
        if error:
            return f"Não consegui validar pelo Poco: {error}"
        if result.get("internet_validated"):
            return "Validação pelo Poco: Wi-Fi conectado e internet confirmada pelo Android."
        if result.get("wifi_connected"):
            return "Validação pelo Poco: Wi-Fi conectado, mas sem acesso à internet confirmado."
        return "Validação pelo Poco: Wi-Fi desconectado."

    async def _poco_saneago_bills(self, params: dict | None = None) -> str:
        try:
            await self.app.bot.send_message(
                chat_id=Config.ALLOWED_USER_ID,
                text="Consultando a Saneago no Poco pelo app oficial. Pode levar alguns minutos; aviso assim que terminar.",
            )
        except Exception:
            logger.debug("Não foi possível enviar o aviso intermediário da Saneago", exc_info=True)
        property_key = (params or {}).get("property", "casa")
        result, error = await self._run_poco_job(
            "refresh_saneago_bills",
            Config.POCO_BILL_JOB_TIMEOUT_SECONDS,
            {"property": property_key},
        )
        if error:
            fallback = await self._poco_bill_cache_note("saneago", property_key)
            if "acessibilidade nao respondeu" in error.lower() or "acessibilidade não respondeu" in error.lower():
                return "A automação do ROD está desativada no Poco. Abra Configurações > Acessibilidade > Aplicativos baixados e ative ROD — automação local." + fallback
            if "Sessao Saneago expirada" in error:
                return "A sessão da Saneago expirou. O ROD tentará entrar novamente usando o cofre local do Poco." + fallback
            if "numero da conta" in error.lower():
                return "Li a tela da Saneago mas não consegui confirmar o número da conta. Não vou atribuir essa fatura a nenhum imóvel sem essa confirmação." + fallback
            if "nao apareceu no seletor" in error.lower():
                name = property_key.replace("_", " ").title()
                return f"A unidade {name} não aparece entre as contas vinculadas a este login da Saneago. Não usei dados de outro imóvel."
            return f"Não consegui consultar a Saneago agora: {error}" + fallback
        return (
            "Saneago — consulta real pelo app oficial\n"
            f"Imóvel: {property_key.replace('_', ' ').title()}\n"
            f"Conta: {result.get('account', 'indisponível')}\n"
            f"Fatura: {result.get('amount', 'indisponível')}\n"
            f"Referência: {result.get('reference', 'indisponível')}\n"
            f"Vencimento: {result.get('due_date', 'indisponível')}\n"
            f"Consumo: {result.get('consumption', 'indisponível')}"
        )

    async def _poco_equatorial_bills(self, params: dict | None = None) -> str:
        property_key = (params or {}).get("property", "casa")
        try:
            await self.app.bot.send_message(
                chat_id=Config.ALLOWED_USER_ID,
                text="Consultando a Equatorial no Poco pelo portal oficial. Pode levar alguns minutos; aviso assim que terminar.",
            )
        except Exception:
            logger.debug("Não foi possível enviar o aviso intermediário da Equatorial", exc_info=True)
        result, error = await self._run_poco_job(
            "refresh_equatorial_bills",
            Config.POCO_BILL_JOB_TIMEOUT_SECONDS,
            {"property": property_key},
        )
        if error:
            fallback = await self._poco_bill_cache_note("equatorial", property_key)
            if any(marker in error.lower() for marker in ("captcha", "imperva", "verificacao humana")):
                return "A Equatorial pediu verificação humana no Poco. Resolva a tela uma vez e repita a consulta; o ROD não tenta contornar o bloqueio." + fallback
            return f"Não consegui consultar a Equatorial agora: {error}" + fallback
        return (
            "Equatorial — consulta real pelo portal oficial\n"
            f"Imóvel: {property_key.replace('_', ' ').title()}\n"
            f"Fatura: {result.get('amount', 'indisponível')}\n"
            f"Referência: {result.get('reference', 'indisponível')}\n"
            f"Vencimento: {result.get('due_date', 'indisponível')}"
        )

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
            self.pending_actions[chat_id] = {
                "intent": "network_block_device",
                "action": "block",
                "params": {"ip": ip, "confirmed": True},
            }
            await query.edit_message_text(
                f"Bloquear o dispositivo {ip} no AdGuard?\n\nDigite confirmar para executar ou cancelar para abortar."
            )
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
