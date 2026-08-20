import html
import inspect
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

# =====================================================
# CONTAS & FATURAS — CONTRATO COM O NÓ POCO
# =====================================================
# As ações de artefato pertencem à fila do nó Android. Ficam nomeadas aqui, num
# lugar só, para que ligar/desligar o contrato seja uma linha e não uma caçada
# pelo arquivo. Nenhuma delas paga, confirma ou movimenta qualquer valor.
POCO_PIX_ACTION = "get_equatorial_pix"
POCO_BOLETO_ACTION = "get_equatorial_boleto"

# Um artefato de pagamento só é reaproveitado dentro da MESMA fatura e por pouco
# tempo. Sem o limite, um toque em PIX no mês seguinte devolveria o código do mês
# anterior — erro caro e silencioso.
BILL_ARTIFACT_TTL_SECONDS = 900

# Imóveis que já tiveram uma leitura concluída. É a única prova local de que a
# unidade existe no cofre do Poco; o heartbeat expõe contagem, não nomes.
BILL_STATE_KEY = "bill_properties_confirmed"

# Mensagens de falha que o dono lê. Código tipado, nome de exceção e traceback
# ficam no log; na tela fica o que dá para fazer a respeito.
POCO_UNAVAILABLE_MESSAGE = "📱 O Poco está temporariamente indisponível. Tente novamente."
PORTAL_UNAVAILABLE_MESSAGE = "⚡ A Equatorial não respondeu agora. Tente novamente em alguns minutos."
HUMAN_CHECK_ALL_CHANNELS_MESSAGE = (
    "⚠️ A Equatorial exigiu verificação humana em todos os canais automáticos "
    "disponíveis. Nenhum pagamento foi realizado."
)
BILL_GENERIC_FAILURE_MESSAGE = (
    "Não consegui consultar a Equatorial agora. Tente novamente em alguns minutos."
)
BILL_ACTION_UNAVAILABLE_MESSAGE = (
    "Essa opção ainda não está habilitada no Poco. A consulta continua funcionando e "
    "nenhum pagamento foi realizado."
)
BILL_ARTIFACT_UNAVAILABLE_MESSAGE = (
    "Não recebi o arquivo do Poco. Nenhum pagamento foi realizado; tente novamente em "
    "alguns minutos."
)
PROVIDER_LABELS = {"equatorial": "Equatorial", "saneago": "Saneago"}


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
        # Single-flight de contas: uma automação por (concessionária, imóvel, ação).
        # O Poco executa um job por vez, então dois toques rápidos no mesmo botão
        # não criavam duas leituras — criavam uma fila que dobrava a espera.
        self._bill_flights: Dict[tuple, Any] = {}
        # Artefato de pagamento em memória, nunca em disco e nunca em log.
        self._bill_artifacts: Dict[tuple, Dict[str, Any]] = {}
        # Referência da última leitura confirmada, para provar que o artefato
        # entregue é da mesma fatura que está na tela.
        self._bill_reference: Dict[tuple, str] = {}
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

                "🧾 **CONTAS & FATURAS**\n"
                "• `conta de luz casa` → Consulta a Equatorial no portal oficial pelo Poco.\n"
                "• `conta de agua kitnet 01` → Consulta a Saneago pelo app oficial.\n"
                "• No resultado: botões de Pix copia e cola, boleto em PDF e atualizar.\n"
                "• Nenhum pagamento é iniciado; o ROD só entrega o código e o arquivo.\n\n"

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
                    "🖥️ **Sistema** → Monitoramento, controle\n"
                    "🧾 **Contas & Faturas** → Energia e água pelo Poco\n\n"
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
            return self._bills_menu()

        # --- END SUBMENUS ---

        if intent == "system_status": return await SystemModule.get_status()
        if intent == "poco_status":
            return await self._poco_status()
        if intent == "poco_network_check":
            return await self._poco_network_check()
        if intent == "saneago_bills":
            return await self._poco_saneago_bills(params)
        if intent == "equatorial_bills":
            return await self._equatorial_bill_flow(chat_id, (params or {}).get("property", "casa"))
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

    @staticmethod
    def _equatorial_code(error_text: str) -> str:
        """Código tipado emitido pelo agente Android, venha ele embrulhado ou não.

        O agente monta a mensagem como ``classe: mensagem`` antes de devolvê-la,
        então o que chega no fio é ``IllegalStateException: EQUATORIAL_...``.
        Casar pelo início da string parecia certo e nunca funcionou: dos 37 erros
        registrados em produção, nenhum começava com ``EQUATORIAL_`` e todos
        começavam com o nome da exceção. Procurar o código em qualquer posição
        sobrevive a qualquer embrulho que o Android venha a usar.
        """
        match = re.search(r"\b(EQUATORIAL_[A-Z_]+)", error_text or "")
        return match.group(1) if match else ""

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
        """Texto da consulta, sem tocar no Telegram.

        Quem manda mensagem é o fluxo (``_equatorial_bill_flow``): a UX pede UMA
        mensagem editada no fim, e um aviso intermediário aqui deixava duas.
        """
        property_key = (params or {}).get("property", "casa")
        result, failure = await self._equatorial_bill_read(property_key)
        if failure:
            return failure
        return self._format_equatorial_bill(property_key, result)

    async def _equatorial_bill_read(self, property_key: str):
        """(resultado, mensagem de falha já humanizada)."""
        result, error = await self._run_poco_job(
            "refresh_equatorial_bills",
            Config.POCO_BILL_JOB_TIMEOUT_SECONDS,
            {"property": property_key},
        )
        if error:
            fallback = await self._poco_bill_cache_note("equatorial", property_key)
            return None, self._equatorial_failure_message(str(error).strip(), property_key) + fallback
        return result or {}, None

    def _equatorial_failure_message(self, error_text: str, property_key: str) -> str:
        """Traduz a falha para uma frase que o dono pode agir a respeito.

        Nada de ``IllegalStateException``, traceback ou código ``EQUATORIAL_*`` na
        tela: eles não dizem ao dono o que fazer e vazam detalhe de automação. O
        código continua no log, que é onde ele serve para algo.
        """
        text = str(error_text or "")
        lowered = text.lower()
        # Erros tipados do agente Android vêm antes da heurística por palavra-chave.
        # Sessão expirada não é falha de infraestrutura: pedir login humano uma vez
        # é mais honesto (e mais barato) do que repetir tentativas cegas no Poco.
        code = self._equatorial_code(text)
        logger.info("Falha na Equatorial classificada como %s", code or "sem código tipado")

        # Verificação humana em TODOS os canais é diferente de um desafio numa tela:
        # não existe próximo passo automático, e o dono precisa ouvir que nada foi pago.
        if code == "EQUATORIAL_HUMAN_CHECK_ALL_CHANNELS" or "todos os canais" in lowered:
            return HUMAN_CHECK_ALL_CHANNELS_MESSAGE

        if code == "EQUATORIAL_AUTH_REQUIRED":
            return (
                "A sessão da Equatorial expirou no Poco. Abra o Chrome do Poco e faça "
                "login novamente na Equatorial; depois repita a consulta."
            )
        if code == "EQUATORIAL_HUMAN_CHECK" or any(
            marker in lowered for marker in ("captcha", "imperva", "verificacao humana")
        ):
            return (
                "A Equatorial pediu verificação humana no Poco. Resolva a tela uma vez e "
                "repita a consulta; o ROD não tenta contornar o bloqueio."
            )
        # Cada código diz o que fazer. Devolver só "falhou" obrigaria abrir o
        # logcat do Poco para descobrir se o problema é do portal, do cadastro
        # ou da leitura.
        typed = {
            # O portal recusa login automático em silêncio: recarrega a tela de
            # acesso sem dizer nada. O motivo é o motor antifraude dele, que
            # pontua a sessão em vez de apresentar desafio. Não há o que o dono
            # conserte no cadastro, então a mensagem não manda procurar defeito.
            "EQUATORIAL_LOGIN_FAILED": (
                "A Equatorial não aceitou a entrada automática — o portal dela avalia o acesso "
                "por um sistema antifraude e recusou sem informar motivo. Abrir o Chrome do Poco "
                "e entrar uma vez restabelece a consulta. Nenhum pagamento foi feito."
            ),
            "EQUATORIAL_LOGIN_REJECTED": (
                "A Equatorial recusou os dados de acesso guardados no cofre do Poco. "
                "Vale conferir a unidade consumidora e o documento cadastrados."
            ),
            "EQUATORIAL_CREDENTIALS_MISSING": (
                "Faltam dados de acesso da Equatorial no cofre do Poco. "
                "Cadastre unidade consumidora e documento no aplicativo ROD."
            ),
            "EQUATORIAL_WEBVIEW_UNAVAILABLE": (
                "O navegador interno do ROD não subiu no Poco desta vez. Vale repetir a consulta."
            ),
            "EQUATORIAL_PIX_NOT_FOUND": (
                "Não encontrei o Pix desta fatura na tela do portal. Nenhum pagamento foi feito."
            ),
            "EQUATORIAL_PIX_AMBIGUOUS": (
                "O portal mostrou mais de um código Pix e não consigo saber qual é desta fatura. "
                "Prefiro não enviar nada a enviar o Pix de outra conta."
            ),
            "EQUATORIAL_PIX_INVALID": (
                "O código Pix que li não passou na validação oficial do BR Code. "
                "Não vou entregar um código de pagamento que pode estar corrompido."
            ),
            "EQUATORIAL_BOLETO_NOT_FOUND": (
                "O portal não ofereceu o boleto desta fatura agora. Tente novamente em alguns minutos."
            ),
            "EQUATORIAL_BOLETO_TOO_LARGE": (
                "O arquivo do boleto veio maior do que o limite seguro e foi descartado."
            ),
            "EQUATORIAL_BOLETO_NOT_SENT": (
                "Consegui o boleto mas falhei ao entregá-lo. Tente novamente."
            ),
            "EQUATORIAL_PROPERTY_NOT_MAPPED": (
                f"Ainda não sei qual conta contrato do portal corresponde a "
                f"{self._property_label(property_key)}. O ROD aprende isso sozinho na "
                "primeira consulta bem-sucedida; se persistir, confira a unidade consumidora "
                "cadastrada no cofre do Poco."
            ),
            # Sinônimo emitido hoje pelo agente Android.
            "EQUATORIAL_UC_NAO_ENCONTRADA": (
                "O imóvel pedido não apareceu na lista de contratos desse login da Equatorial. "
                "Não usei dados de outro imóvel."
            ),
            "EQUATORIAL_CONTRACT_NOT_FOUND": (
                "O imóvel pedido não apareceu na lista de contratos desse login da Equatorial. "
                "Não usei dados de outro imóvel."
            ),
            "EQUATORIAL_BILL_NOT_FOUND": (
                "Cheguei ao imóvel certo no portal, mas nenhuma fatura estava visível na tela. "
                "Pode não haver fatura em aberto agora."
            ),
            "EQUATORIAL_PAYMENT_DATA_NOT_FOUND": (
                "Li a fatura, mas o portal não expôs código de barras nem PIX nesta tela. "
                "Não vou inventar um código de pagamento."
            ),
            "EQUATORIAL_PORTAL_TIMEOUT": (
                "O portal da Equatorial não respondeu a tempo no Poco. "
                "Vale repetir a consulta em alguns minutos."
            ),
        }
        if code in typed:
            return typed[code]

        # Falha de infraestrutura do nó: não é problema da concessionária e não há
        # o que o dono resolva no portal.
        if any(
            marker in lowered
            for marker in (
                "poco está offline",
                "poco esta offline",
                "sem heartbeat",
                "nó poco está desativado",
                "no poco esta desativado",
                "não confirmou o início",
                "nao confirmou o inicio",
            )
        ):
            return POCO_UNAVAILABLE_MESSAGE

        # Portal fora do ar sem código tipado (5xx, DNS, conexão recusada).
        if any(
            marker in lowered
            for marker in ("502", "503", "504", "err_", "net::", "unreachable", "connection")
        ):
            return PORTAL_UNAVAILABLE_MESSAGE

        return BILL_GENERIC_FAILURE_MESSAGE

    def _format_equatorial_bill(self, property_key: str, result: dict | None) -> str:
        result = result or {}
        lines = [
            "Equatorial — consulta real pelo portal oficial",
            f"Imóvel: {self._property_label(property_key)}",
            f"Fatura: {result.get('amount', 'indisponível')}",
            f"Referência: {result.get('reference', 'indisponível')}",
            f"Vencimento: {result.get('due_date', 'indisponível')}",
        ]
        # Código de barras e PIX existem só em parte das faturas. Ausente é ausente:
        # nenhuma linha inventada e nenhum rótulo que o usuário possa ler como leitura real.
        barcode = str(result.get("barcode") or "").strip()
        if barcode:
            lines.append(f"Código de barras: {barcode}")
        pix = str(result.get("pix") or "").strip()
        if pix:
            lines.append(f"PIX: {pix}")
        return "\n".join(lines)

    # =====================================================
    # CONTAS & FATURAS — UX NO TELEGRAM
    # =====================================================
    @staticmethod
    def _property_label(property_key: str) -> str:
        return str(property_key or "casa").replace("_", " ").strip().title()

    @staticmethod
    def _property_phrase(property_key: str) -> str:
        """Frase que o roteador reconhece de volta (`kitnet_01` → `kitnet 01`)."""
        return str(property_key or "casa").replace("_", " ").strip()

    def _flight_in_progress(self, provider: str, property_key: str, action: str) -> bool:
        task = self._bill_flights.get((provider, property_key, action))
        return task is not None and not task.done()

    async def _single_flight(self, provider: str, property_key: str, action: str, factory):
        """Uma automação por (concessionária, imóvel, ação).

        O Poco executa um job por vez. Dois toques rápidos no mesmo botão criavam
        dois jobs iguais: o segundo esperava o primeiro terminar e devolvia o mesmo
        dado depois do dobro do tempo. Aqui o segundo interessado espera a operação
        que já existe. O ``shield`` evita que um chamador que desistiu (timeout do
        Telegram, mensagem apagada) cancele o job de quem ainda espera.

        Devolve ``(resultado, reaproveitado)``.
        """
        key = (provider, property_key, action)
        existing = self._bill_flights.get(key)
        if existing is not None and not existing.done():
            return await asyncio.shield(existing), True
        task = asyncio.ensure_future(factory())
        self._bill_flights[key] = task
        try:
            return await asyncio.shield(task), False
        finally:
            if self._bill_flights.get(key) is task and task.done():
                self._bill_flights.pop(key, None)

    def _bill_keyboard(self, provider: str, property_key: str, *, payment: bool = True):
        try:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        except ImportError:
            return None
        rows = []
        if payment:
            rows.append(
                [
                    InlineKeyboardButton("💠 PIX", callback_data=f"bill_pix:{provider}:{property_key}"),
                    InlineKeyboardButton("📄 BOLETO", callback_data=f"bill_boleto:{provider}:{property_key}"),
                ]
            )
        rows.append(
            [
                InlineKeyboardButton("🔄 ATUALIZAR", callback_data=f"bill_refresh:{provider}:{property_key}"),
                InlineKeyboardButton("🔙 VOLTAR", callback_data="menu_contas"),
            ]
        )
        return InlineKeyboardMarkup(rows)

    async def _send_bill_text(self, chat_id: int, text: str, reply_markup=None, parse_mode=None):
        kwargs = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        try:
            message = await self.app.bot.send_message(**kwargs)
            return getattr(message, "message_id", None)
        except Exception:
            logger.warning("Não consegui enviar a mensagem de fatura no Telegram", exc_info=True)
            return None

    async def _replace_bill_message(self, chat_id: int, message_id, text: str, reply_markup=None):
        """Edita a mensagem da consulta em vez de empilhar avisos no chat.

        Duas mensagens ("estou consultando" e "resultado") viraram poluição real:
        uma consulta leva minutos e o dono ficava com o histórico cheio de avisos
        obsoletos. Falha de edição (mensagem apagada, texto idêntico) não pode
        derrubar o fluxo — cai para uma mensagem nova.
        """
        if message_id is not None:
            try:
                await self.app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                return message_id
            except Exception:
                logger.debug("Edição da mensagem de fatura falhou", exc_info=True)
                return message_id
        return await self._send_bill_text(chat_id, text, reply_markup)

    async def _equatorial_bill_flow(self, chat_id: int, property_key: str, query=None):
        """Consulta com UMA mensagem: abre com o aviso e termina editando-a."""
        provider = "equatorial"
        label = self._property_label(property_key)
        header = f"⚡ Consultando Equatorial — {label}..."
        if query is not None:
            message_id = getattr(getattr(query, "message", None), "message_id", None)
            await self._replace_bill_message(chat_id, message_id, header)
        else:
            message_id = await self._send_bill_text(chat_id, header)

        (text, ok), _reused = await self._single_flight(
            provider, property_key, "bills", lambda: self._equatorial_bill_card(property_key)
        )
        keyboard = self._bill_keyboard(provider, property_key, payment=ok)
        await self._replace_bill_message(chat_id, message_id, text, keyboard)
        return None

    async def _equatorial_bill_card(self, property_key: str):
        """(texto, deu_certo). Nunca levanta: o single-flight é compartilhado."""
        try:
            result, failure = await self._equatorial_bill_read(property_key)
        except Exception:
            logger.exception("Falha inesperada na consulta da Equatorial")
            return BILL_GENERIC_FAILURE_MESSAGE, False
        if failure:
            return failure, False
        self._remember_bill_property("equatorial", property_key)
        reference = str((result or {}).get("reference") or "").strip()
        self._bill_reference[("equatorial", property_key)] = reference
        return self._format_equatorial_bill(property_key, result), True

    # ---------- ARTEFATOS DE PAGAMENTO (PIX / BOLETO) ----------
    async def _run_poco_bill_action(self, action: str, property_key: str):
        """Único ponto de contato com as ações de artefato do nó Android.

        Enquanto a fila do Poco não aceitar a ação, ``enqueue`` levanta
        ``ValueError``; o dono precisa de uma frase honesta, não de um traceback.
        """
        try:
            result, error = await self._run_poco_job(
                action,
                Config.POCO_BILL_JOB_TIMEOUT_SECONDS,
                {"provider": "equatorial", "property": property_key},
            )
        except ValueError:
            logger.info("Ação de artefato ainda não habilitada na fila do Poco: %s", action)
            return None, BILL_ACTION_UNAVAILABLE_MESSAGE
        except Exception:
            logger.exception("Falha ao enfileirar ação de artefato no Poco")
            return None, POCO_UNAVAILABLE_MESSAGE
        if error:
            return None, self._equatorial_failure_message(str(error).strip(), property_key)
        return result or {}, None

    @staticmethod
    def _artifact_store():
        """Canal de artefato do Pi, se já existir nesta versão.

        Concentrar a dependência num método só significa que trocar o contrato
        (hoje ``get_artifact_store().resolve``/``consume``) é uma edição local, e
        que a ausência do canal vira frase honesta em vez de traceback.
        """
        try:
            from jarvis.api import app as api_app

            factory = getattr(api_app, "get_artifact_store", None)
            return factory() if callable(factory) else None
        except Exception:
            logger.warning("Canal de artefato indisponível", exc_info=True)
            return None

    async def _resolve_poco_artifact(self, artifact_id):
        """Traduz o id opaco em caminho de arquivo temporário local."""
        if not artifact_id:
            return None, BILL_ARTIFACT_UNAVAILABLE_MESSAGE
        resolvers = []
        store = self._artifact_store()
        if store is not None:
            resolvers.append(getattr(store, "resolve", None))
        try:
            from jarvis.api import app as api_app

            resolvers.append(getattr(api_app, "resolve_poco_artifact", None))
        except Exception:
            logger.debug("API local indisponível para resolver artefato", exc_info=True)
        for resolver in resolvers:
            if not callable(resolver):
                continue
            try:
                path = resolver(artifact_id)
                if inspect.isawaitable(path):
                    path = await path
            except Exception:
                logger.warning("Resolução do artefato falhou", exc_info=True)
                return None, BILL_ARTIFACT_UNAVAILABLE_MESSAGE
            if path and os.path.exists(str(path)):
                return str(path), None
            return None, BILL_ARTIFACT_UNAVAILABLE_MESSAGE
        logger.info("Nenhum resolvedor de artefato disponível no Pi ainda")
        return None, BILL_ACTION_UNAVAILABLE_MESSAGE

    def _release_artifact(self, artifact_id, path):
        """Entrega feita: o artefato deixa de existir no Pi.

        Preferir ``consume`` do canal a apagar o arquivo na mão mantém metadados e
        arquivo consistentes; o unlink direto é só a rede de segurança.
        """
        store = self._artifact_store()
        consumer = getattr(store, "consume", None) if store is not None else None
        if artifact_id and callable(consumer):
            try:
                consumer(artifact_id)
                return
            except Exception:
                logger.debug("Não consegui consumir o artefato pelo canal", exc_info=True)
        self._discard_temp_artifact(path)

    @staticmethod
    def _discard_temp_artifact(path):
        """Arquivo de pagamento não fica no disco depois de entregue."""
        if not path:
            return
        try:
            os.unlink(str(path))
        except OSError:
            logger.debug("Não consegui apagar o artefato temporário", exc_info=True)

    @staticmethod
    def _artifact_id(result: dict) -> str:
        for field in ("artifact_id", "artifact", "boleto_artifact_id", "pix_artifact_id"):
            value = str((result or {}).get(field) or "").strip()
            if value:
                return value
        return ""

    def _fresh_artifact(self, provider: str, property_key: str, kind: str):
        """Artefato em memória só serve se for da MESMA fatura e ainda recente."""
        cached = self._bill_artifacts.get((provider, property_key, kind))
        if not cached:
            return None
        if time.time() - cached.get("captured_at", 0) > BILL_ARTIFACT_TTL_SECONDS:
            self._bill_artifacts.pop((provider, property_key, kind), None)
            return None
        current = self._bill_reference.get((provider, property_key), "")
        if current and cached.get("reference") and cached["reference"] != current:
            self._bill_artifacts.pop((provider, property_key, kind), None)
            return None
        return cached

    async def _fetch_pix_payload(self, property_key: str):
        """(payload, referência, falha). Nunca registra o payload em log."""
        result, failure = await self._run_poco_bill_action(POCO_PIX_ACTION, property_key)
        if failure:
            return "", "", failure
        reference = str(result.get("reference") or "").strip() or self._bill_reference.get(
            ("equatorial", property_key), ""
        )
        payload = ""
        for field in ("pix_payload", "payload", "pix", "copia_e_cola"):
            candidate = str(result.get(field) or "").strip()
            if candidate:
                payload = candidate
                break
        if not payload:
            artifact_id = self._artifact_id(result)
            if artifact_id:
                path, artifact_failure = await self._resolve_poco_artifact(artifact_id)
                if artifact_failure:
                    return "", reference, artifact_failure
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as handle:
                        payload = handle.read().strip()
                except OSError:
                    logger.warning("Não consegui ler o artefato do Pix", exc_info=True)
                finally:
                    self._release_artifact(artifact_id, path)
        if not payload:
            return "", reference, (
                "O Poco não devolveu o Pix desta fatura. Não vou inventar um código de pagamento."
            )
        # Pix copia e cola é texto. Link é caminho para iniciar pagamento, e o ROD
        # não inicia pagamento nenhum.
        if "http://" in payload.lower() or "https://" in payload.lower():
            return "", reference, (
                "O que voltou do portal não é um Pix copia e cola. Não vou enviar link de pagamento."
            )
        return payload, reference, None

    async def _send_bill_pix(self, chat_id: int, property_key: str, query=None):
        provider = "equatorial"
        label = self._property_label(property_key)
        if self._flight_in_progress(provider, property_key, "pix"):
            await self._send_bill_text(
                chat_id, f"⏳ Já estou buscando o Pix da Equatorial — {label}. Aguarde."
            )
            return None
        cached = self._fresh_artifact(provider, property_key, "pix")
        if cached:
            await self._deliver_pix(chat_id, property_key, cached["payload"], cached.get("reference", ""))
            return None
        (payload, reference, failure), _reused = await self._single_flight(
            provider, property_key, "pix", lambda: self._fetch_pix_payload(property_key)
        )
        if failure:
            await self._send_bill_text(chat_id, failure)
            return None
        self._bill_artifacts[(provider, property_key, "pix")] = {
            "payload": payload,
            "reference": reference,
            "captured_at": time.time(),
        }
        await self._deliver_pix(chat_id, property_key, payload, reference)
        return None

    async def _deliver_pix(self, chat_id: int, property_key: str, payload: str, reference: str):
        """Só o código, em bloco, para copiar com um toque. Nenhum link."""
        label = self._property_label(property_key)
        title = f"Pix copia e cola — Equatorial {label} — ref. {reference or 'indisponível'}"
        sent = await self._send_bill_text(
            chat_id,
            f"{title}\n<pre>{html.escape(payload)}</pre>",
            parse_mode="HTML",
        )
        if sent is None:
            # Sem HTML o payload ainda precisa chegar legível e copiável.
            await self._send_bill_text(chat_id, f"{title}\n\n{payload}")
        return None

    async def _fetch_boleto_file(self, property_key: str):
        """({caminho, referência, artifact_id}, falha)."""
        result, failure = await self._run_poco_bill_action(POCO_BOLETO_ACTION, property_key)
        if failure:
            return {}, failure
        reference = str(result.get("reference") or "").strip() or self._bill_reference.get(
            ("equatorial", property_key), ""
        )
        artifact_id = self._artifact_id(result)
        path, artifact_failure = await self._resolve_poco_artifact(artifact_id)
        if artifact_failure:
            return {"reference": reference}, artifact_failure
        return {"path": path, "reference": reference, "artifact_id": artifact_id}, None

    @staticmethod
    def _safe_bill_filename(provider: str, property_key: str, reference: str, extension: str = "pdf") -> str:
        """Nome construído pelo Pi, nunca o nome que veio do portal.

        Nome de arquivo remoto é entrada não confiável: serve para travessia de
        diretório e para vazar dado do cadastro no chat. O dono continua vendo um
        nome amigável porque ele é montado aqui, com dados que já estão na tela.
        """
        parts = [
            PROVIDER_LABELS.get(provider, str(provider or "").title()),
            Executor._property_label(property_key).replace(" ", "-"),
            str(reference or ""),
        ]
        cleaned = []
        for part in parts:
            safe = re.sub(r"[^0-9A-Za-z]+", "-", str(part)).strip("-")
            if safe:
                cleaned.append(safe)
        name = "_".join(cleaned) or "Boleto"
        safe_extension = re.sub(r"[^0-9A-Za-z]+", "", str(extension or "pdf")) or "pdf"
        return f"{name[:60]}.{safe_extension}"

    async def _send_bill_boleto(self, chat_id: int, property_key: str, query=None):
        provider = "equatorial"
        label = self._property_label(property_key)
        if self._flight_in_progress(provider, property_key, "boleto"):
            await self._send_bill_text(
                chat_id, f"⏳ Já estou buscando o boleto da Equatorial — {label}. Aguarde."
            )
            return None
        (info, failure), _reused = await self._single_flight(
            provider, property_key, "boleto", lambda: self._fetch_boleto_file(property_key)
        )
        path = (info or {}).get("path")
        reference = (info or {}).get("reference", "")
        if failure or not path:
            await self._send_bill_text(chat_id, failure or BILL_ARTIFACT_UNAVAILABLE_MESSAGE)
            return None
        filename = self._safe_bill_filename(provider, property_key, reference)
        caption = f"📄 Boleto Equatorial — {label} — referência {reference or 'indisponível'}"
        try:
            with open(path, "rb") as handle:
                await self.app.bot.send_document(
                    chat_id=chat_id,
                    document=handle,
                    filename=filename,
                    caption=caption,
                )
        except Exception:
            logger.warning("Falha ao enviar o boleto pelo Telegram", exc_info=True)
            await self._send_bill_text(
                chat_id,
                "Não consegui entregar o boleto agora. Nenhum pagamento foi realizado; "
                "tente novamente em alguns minutos.",
            )
        finally:
            # O Telegram já respondeu (sucesso ou erro): o PDF de pagamento não fica
            # no disco do Pi em nenhum dos dois casos.
            self._release_artifact((info or {}).get("artifact_id"), path)
        return None

    async def handle_bill_callback(self, chat_id: int, data: str, query):
        """Callbacks ``bill_*``: menu do imóvel, PIX, boleto e atualizar."""
        if chat_id != Config.ALLOWED_USER_ID:
            logger.warning("Callback de fatura bloqueado (chat não autorizado)")
            return None
        raw = str(data or "")
        parts = raw.split(":")
        action = parts[0][len("bill_"):] if parts[0].startswith("bill_") else ""
        if len(parts) >= 3:
            provider, property_key = parts[1], parts[2]
        elif len(parts) == 2:
            provider, property_key = "equatorial", parts[1]
        else:
            provider, property_key = "equatorial", "casa"

        if action == "menu":
            payload = self._bill_property_menu(property_key)
            await self._replace_bill_message(
                chat_id,
                getattr(getattr(query, "message", None), "message_id", None),
                payload["text"],
                payload.get("reply_markup"),
            )
            return None

        if provider != "equatorial":
            await self._send_bill_text(chat_id, BILL_ACTION_UNAVAILABLE_MESSAGE)
            return None

        # Sem esta rede, uma exceção inesperada subiria até o handler genérico do
        # main, que responde "Deu ruim aqui" com o texto do erro — exatamente o
        # detalhe técnico que esta tela não pode mostrar.
        try:
            if action == "refresh":
                return await self._equatorial_bill_flow(chat_id, property_key, query=query)
            if action == "pix":
                return await self._send_bill_pix(chat_id, property_key, query=query)
            if action == "boleto":
                return await self._send_bill_boleto(chat_id, property_key, query=query)
        except Exception:
            logger.exception("Falha inesperada no botão de fatura")
            await self._send_bill_text(chat_id, BILL_GENERIC_FAILURE_MESSAGE)
            return None

        logger.warning("Callback de fatura desconhecido")
        await self._send_bill_text(chat_id, "Não reconheci esse botão de fatura.")
        return None

    # ---------- MENU DE CONTAS ----------
    def _poco_heartbeat(self):
        if not Config.POCO_NODE_ENABLED:
            return None
        try:
            from jarvis.api.app import get_poco_service

            status = get_poco_service().status() or {}
        except Exception:
            logger.debug("Não consegui ler o heartbeat do Poco", exc_info=True)
            return None
        if not status.get("online"):
            return None
        heartbeat = status.get("heartbeat")
        return heartbeat if isinstance(heartbeat, dict) else None

    @staticmethod
    def _confirmed_bill_properties() -> Dict[str, List[str]]:
        try:
            stored = Persistence.get_state(BILL_STATE_KEY, {}) or {}
        except Exception:
            logger.debug("Não consegui ler os imóveis confirmados", exc_info=True)
            return {}
        if not isinstance(stored, dict):
            return {}
        clean: Dict[str, List[str]] = {}
        for provider, keys in stored.items():
            if isinstance(keys, list):
                clean[str(provider)] = [str(key) for key in keys if isinstance(key, str)]
        return clean

    def _remember_bill_property(self, provider: str, property_key: str) -> None:
        """Só uma leitura concluída prova que o imóvel existe no cofre do Poco."""
        current = self._confirmed_bill_properties()
        keys = current.setdefault(provider, [])
        if property_key in keys:
            return
        keys.append(property_key)
        try:
            Persistence.set_state(BILL_STATE_KEY, current)
        except Exception:
            logger.debug("Não consegui registrar o imóvel confirmado", exc_info=True)

    def _bills_menu(self) -> Dict[str, Any]:
        """Botões só para imóveis realmente confirmados.

        LIMITAÇÃO CONHECIDA: o heartbeat do Poco expõe apenas ``water_units`` e
        ``energy_units`` — contagens, sem os nomes das unidades. Não existe, hoje,
        como derivar a lista de imóveis do cofre, então o menu mostra o que uma
        consulta bem-sucedida já provou e diz em voz alta o que ainda não sabe, em
        vez de inventar cinco botões plausíveis.
        """
        heartbeat = self._poco_heartbeat()
        confirmed = self._confirmed_bill_properties()
        properties = sorted({key for keys in confirmed.values() for key in keys})

        rows = []
        try:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        except ImportError:
            InlineKeyboardMarkup = InlineKeyboardButton = None  # type: ignore

        if InlineKeyboardButton is not None:
            for key in properties:
                rows.append(
                    [
                        InlineKeyboardButton(
                            f"🏠 {self._property_label(key)}", callback_data=f"bill_menu:{key}"
                        )
                    ]
                )
            rows.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="help")])
            reply_markup = InlineKeyboardMarkup(rows)
        else:
            reply_markup = None

        lines = ["🧾 CONTAS & FATURAS", ""]
        if properties:
            lines.append("Imóveis com consulta já concluída (é a lista que eu posso provar):")
        else:
            lines.append("Ainda não concluí nenhuma consulta, então não tenho imóvel confirmado.")
        if heartbeat:
            lines.append(
                f"O Poco reporta {int(heartbeat.get('energy_units') or 0)} unidade(s) de energia e "
                f"{int(heartbeat.get('water_units') or 0)} de água no cofre — só a contagem, "
                "sem os nomes."
            )
        else:
            lines.append("O Poco não está reportando agora, então não sei o que está no cofre.")
        lines.append("")
        lines.append(
            "Para um imóvel que não aparece aqui, peça uma vez pelo nome — por exemplo "
            "conta de luz kitnet 01. Depois de concluir, ele entra neste menu."
        )
        return {"text": "\n".join(lines), "reply_markup": reply_markup}

    def _bill_property_menu(self, property_key: str) -> Dict[str, Any]:
        """Dentro do imóvel: só a concessionária que está configurada."""
        heartbeat = self._poco_heartbeat()
        confirmed = self._confirmed_bill_properties()
        label = self._property_label(property_key)

        water = property_key in confirmed.get("saneago", [])
        energy = property_key in confirmed.get("equatorial", [])
        if heartbeat:
            if not heartbeat.get("saneago_configured", True):
                water = False
            if not heartbeat.get("equatorial_configured", True):
                energy = False

        rows = []
        try:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        except ImportError:
            InlineKeyboardMarkup = InlineKeyboardButton = None  # type: ignore

        if InlineKeyboardButton is not None:
            provider_row = []
            if water:
                provider_row.append(
                    InlineKeyboardButton(
                        "💧 Água",
                        callback_data=f"conta de agua {self._property_phrase(property_key)}",
                    )
                )
            if energy:
                provider_row.append(
                    InlineKeyboardButton(
                        "⚡ Energia", callback_data=f"bill_refresh:equatorial:{property_key}"
                    )
                )
            if provider_row:
                rows.append(provider_row)
            rows.append([InlineKeyboardButton("🔙 VOLTAR", callback_data="menu_contas")])
            reply_markup = InlineKeyboardMarkup(rows)
        else:
            reply_markup = None

        lines = [f"🧾 {label}", ""]
        if water or energy:
            lines.append("Mostro apenas o que está confirmado para este imóvel.")
        else:
            lines.append(
                "Nenhuma concessionária confirmada para este imóvel agora. "
                "Peça pelo nome uma vez (conta de luz ou conta de água) para eu confirmar."
            )
        return {"text": "\n".join(lines), "reply_markup": reply_markup}

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
