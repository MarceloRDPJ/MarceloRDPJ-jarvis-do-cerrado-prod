import logging
import asyncio
import os
import re
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)

from jarvis.config import Config

from jarvis.core.executor import Executor
from jarvis.core import router
from jarvis.database.persistence import Persistence
from jarvis.core.events import Event

from jarvis.services.collector import CollectorService
from jarvis.services.scheduler import SchedulerService
from jarvis.services.guardian import GuardianService
from jarvis.services.fan_control import FanControlService

import uvicorn

# =====================================================
# LOGGING — SANITIZAÇÃO DE SEGREDOS
# =====================================================
_SANITIZE_PATTERNS = []
_SENSITIVE_ENV_NAMES = ("TOKEN", "API_KEY", "SECRET", "PASSWORD", "PASS", "KEY")


def _add_secret_pattern(value, label):
    if value and isinstance(value, str) and len(value) >= 6:
        _SANITIZE_PATTERNS.append((re.escape(value), label))


token = getattr(Config, "TELEGRAM_TOKEN", None)
_add_secret_pattern(token, "TELEGRAM_TOKEN")
for env_name, env_value in os.environ.items():
    upper_name = env_name.upper()
    if any(marker in upper_name for marker in _SENSITIVE_ENV_NAMES):
        _add_secret_pattern(env_value, upper_name)

_TELEGRAM_BOT_URL_RE = re.compile(r"bot\d+:[A-Za-z0-9_\-]+")


def sanitize_log_text(value: str) -> str:
    if not isinstance(value, str):
        return value
    value = _TELEGRAM_BOT_URL_RE.sub("bot***TELEGRAM_TOKEN***", value)
    for pattern, replacement in _SANITIZE_PATTERNS:
        value = re.sub(pattern, f"***{replacement}***", value)
    return value


class SecretSanitizingFormatter(logging.Formatter):
    def format(self, record):
        return sanitize_log_text(super().format(record))

class SecretSanitizer(logging.Filter):
    """Mascara tokens e chaves de API em todas as mensagens de log."""
    def filter(self, record):
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = sanitize_log_text(record.msg)
        if hasattr(record, "args") and record.args:
            sanitized = []
            for arg in record.args:
                if isinstance(arg, str):
                    arg = sanitize_log_text(arg)
                sanitized.append(arg)
            record.args = tuple(sanitized)
        return True

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
for handler in logging.root.handlers:
    handler.addFilter(SecretSanitizer())
    handler.setFormatter(SecretSanitizingFormatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s"))
# Also sanitize httpx/urllib3 (Telegram API logs the full URL)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("Jarvis")


# =====================================================
# COMMANDS
# =====================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🟢 *Jarvis do Cerrado online.*\n"
        "Guardião da casa ativado.\n\n"
        "Fala o trem aí 👊",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    executor: Executor = context.application.bot_data["executor"]
    response = await executor.execute({"intent": "help", "action": "show", "params": {}}, chat_id)
    if isinstance(response, dict):
        await update.message.reply_text(
            response.get("text", ""),
            reply_markup=response.get("reply_markup"),
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(response, parse_mode="Markdown")


# =====================================================
# MESSAGE HANDLER
# =====================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Segurança básica
    if update.effective_user.id != Config.ALLOWED_USER_ID:
        logger.warning("Mensagem bloqueada (usuário não autorizado)")
        return

    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    logger.info(f"[MSG] {text}")

    await context.bot.send_chat_action(chat_id, "typing")

    try:
        # Roteamento Centralizado (Regras -> NLP -> IA)
        intent = await router.route(text, chat_id)

        executor: Executor = context.application.bot_data["executor"]
        response = await executor.execute(intent, chat_id)

        # Se a resposta for explicitamente None, o Executor já tratou (enviou mensagem direta)
        if response is None:
            return

        if not response:
            logger.warning(f"Executor returned empty response for intent: {intent}")
            response = "🤖 Não entendi direito ainda, uai. (Debug: Resposta vazia do executor)"

        if isinstance(response, dict):
            await update.message.reply_text(
                response.get("text", ""),
                reply_markup=response.get("reply_markup"),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.exception("Erro crítico no handle_message")
        error_msg = f"❌ Deu ruim aqui.\n\n`{str(e)}`"
        await update.message.reply_text(error_msg, parse_mode="Markdown")


# =====================================================
# CALLBACK HANDLER (INTERATIVIDADE)
# =====================================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Segurança básica (callback também precisa)
    if update.effective_user.id != Config.ALLOWED_USER_ID:
        return

    text = query.data
    chat_id = update.effective_chat.id

    logger.info(f"[CALLBACK] {text}")

    # Detecta callbacks de lembretes
    if text.startswith("rem_"):
        from jarvis.core.reminder_callbacks import ReminderCallbacks
        try:
            parts = text.split("_")
            if len(parts) < 3:
                logger.warning(f"Callback rem_ malformatado: {text}")
                await query.message.reply_text("❌ Callback inválido.")
                return
            action = parts[1]
            task_id = int(parts[2])

            if action == "done":
                await ReminderCallbacks.handle_done(task_id, chat_id, query)
                return

            elif action == "snooze":
                if len(parts) < 4:
                    await query.message.reply_text("❌ Callback snooze inválido (sem minutos).")
                    return
                minutes = int(parts[3])
                await ReminderCallbacks.handle_snooze(task_id, chat_id, minutes, query)
                return

            elif action == "cancel":
                await ReminderCallbacks.handle_cancel(task_id, chat_id, query)
                return

            elif action == "reschedule":
                await ReminderCallbacks.handle_reschedule_request(task_id, chat_id, query)
                return
            else:
                logger.warning(f"Ação de callback desconhecida: {action}")
                await query.message.reply_text("❌ Ação de callback desconhecida.")
                return
        except (ValueError, IndexError) as e:
            logger.warning(f"Erro ao parsear callback rem_: {e}")
            await query.message.reply_text("❌ Erro ao processar callback.")
            return

    # Detecta snooze de hidratação
    if text == "agora nao":
        from jarvis.modules.hydration import HydrationModule
        await HydrationModule.snooze_hydration(chat_id, query, minutes=15)
        return

    # Detecta callbacks de rede
    if text.startswith("net_"):
        executor: Executor = context.application.bot_data["executor"]
        await executor.handle_network_callback(chat_id, text, query)
        return

    try:
        # Processa como se fosse texto (simula comando)
        intent = await router.route(text, chat_id)
        executor: Executor = context.application.bot_data["executor"]
        response = await executor.execute(intent, chat_id)

        # Se a resposta for explicitamente None, o Executor já tratou
        if response is None:
            return

        if not response:
             logger.warning(f"Executor callback returned empty response for: {text}")
             response = "🤖 Não entendi direito ainda, uai. (Debug: Callback vazio)"

        # Responde como nova mensagem (padrão chatbot)
        if isinstance(response, dict):
             await query.message.reply_text(
                 response.get("text", ""),
                 reply_markup=response.get("reply_markup"),
                 parse_mode="Markdown"
             )
        else:
             await query.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.exception("Erro crítico no handle_callback")
        error_msg = f"❌ Deu ruim aqui.\n\n`{str(e)}`"
        try:
            await query.message.reply_text(error_msg, parse_mode="Markdown")
        except:
            pass


# =====================================================
# POST INIT (BOOTSTRAP REAL)
# =====================================================
async def post_init(application):
    """
    Executado após o bot subir.
    Aqui nasce o Jarvis de verdade.
    """

    logger.info("🚀 Inicialização pós-start iniciada")

    # -------------------------
    # BANCO
    # -------------------------
    Persistence.init_db()

    Persistence.log_event(
        Event(
            type="system.startup",
            source="main",
            payload={"status": "online"},
        )
    )

    # -------------------------
    # COLETOR AUTOMÁTICO (PASSO 5)
    # -------------------------
    collector = CollectorService(interval_seconds=60)
    scheduler = SchedulerService(application, interval_seconds=30)

    application.bot_data["collector"] = collector
    application.bot_data["scheduler"] = scheduler

    if "tasks" not in application.bot_data:
        application.bot_data["tasks"] = []

    task_collector = asyncio.create_task(collector.start())
    task_scheduler = asyncio.create_task(scheduler.start())

    application.bot_data["tasks"].append(task_collector)
    application.bot_data["tasks"].append(task_scheduler)

    logger.info("📡 Collector e Scheduler iniciados")

    # -------------------------
    # AUTOMATION ENGINE (NOVO)
    # -------------------------
    from jarvis.services.automations import AutomationEngine

    automation = AutomationEngine(application)
    application.bot_data["automation"] = automation
    task_automation = asyncio.create_task(automation.start())
    application.bot_data["tasks"].append(task_automation)
    logger.info("🤖 AutomationEngine iniciado")

    # -------------------------
    # FAN CONTROL SERVICE
    # -------------------------
    fan_service = FanControlService(
        pin=Config.FAN_GPIO_PIN,
        threshold_on=Config.FAN_TEMP_ON,
        threshold_off=Config.FAN_TEMP_OFF
    )
    application.bot_data["fan_service"] = fan_service
    task_fan = asyncio.create_task(fan_service.start())
    application.bot_data["tasks"].append(task_fan)
    logger.info("🌬️ FanControlService acoplado ao ciclo de vida")

    # -------------------------
    # GUARDIAN SERVICE (NOVO)
    # -------------------------
    if Config.ALLOWED_USER_ID:
        guardian = GuardianService(application, chat_id=Config.ALLOWED_USER_ID)
        application.bot_data["guardian"] = guardian
        task_guardian = asyncio.create_task(guardian.start())
        application.bot_data["tasks"].append(task_guardian)
        logger.info("🛡️ GuardianService iniciado")
    else:
        logger.warning("⚠️ ALLOWED_USER_ID não definido. GuardianService não foi iniciado.")

    # -------------------------
    # REPORTER SERVICE (DIARIO / SEMANAL)
    # -------------------------
    from jarvis.services.reporter import ReporterService
    reporter = ReporterService(application)
    application.bot_data["reporter"] = reporter
    task_reporter = asyncio.create_task(reporter.start())
    application.bot_data["tasks"].append(task_reporter)
    logger.info("ReporterService iniciado")

    # -------------------------
    # WEB DASHBOARD API
    # -------------------------
    from jarvis.api.app import app as fastapi_app

    # Inject telegram bot services into FastAPI state
    fastapi_app.state.fan_service = application.bot_data.get("fan_service")
    fastapi_app.state.bot_app = application
    fastapi_app.state.automation_service = application.bot_data.get("automation")

    # Initialize Webhook Manager
    from jarvis.api.webhook_manager import WebhookManager
    webhook_manager = WebhookManager(app_state=fastapi_app.state)
    fastapi_app.state.webhook_manager = webhook_manager
    application.bot_data["webhook_manager"] = webhook_manager
    logger.info("🔗 Webhook Manager inicializado")

    # Initialize MCP Handler
    from jarvis.api.mcp_handler import MCPHandler
    mcp_handler = MCPHandler(fastapi_app.state)
    fastapi_app.state.mcp_handler = mcp_handler
    logger.info("🧠 MCP Handler inicializado")

    # Initialize Integration Engine
    from jarvis.api.integration_engine import IntegrationEngine
    integration_engine = IntegrationEngine(fastapi_app.state)
    fastapi_app.state.integration_engine = integration_engine
    application.bot_data["integration_engine"] = integration_engine
    logger.info("🔌 Integration Engine inicializado")

    # Connect integration engine to guardian events
    guardian = application.bot_data.get("guardian")
    if guardian and integration_engine:
        # Patch guardian to dispatch events to integration engine
        original_check = guardian.check_device_changes

        async def patched_check():
            await original_check()
            # Dispatch events to integration engine
            if hasattr(integration_engine, 'handle_event'):
                try:
                    from jarvis.modules.network import NetworkModule
                    metrics = await NetworkModule.get_ping_metrics()
                    await integration_engine.handle_event(
                        "network.status_changed",
                        {"status": "online" if metrics.get("success") else "down"}
                    )
                except Exception:
                    pass

        guardian.check_device_changes = patched_check

    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    application.bot_data["api_task"] = asyncio.create_task(server.serve())
    logger.info("🌐 Web Dashboard API inicializado")

# =====================================================
# MAIN
# =====================================================
def main():
    if not Config.TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN não configurado")

    application = (
        ApplicationBuilder()
        .token(Config.TELEGRAM_TOKEN)
        .post_init(post_init)


        .build()
    )

    # Executor = cérebro operacional
    application.bot_data["executor"] = Executor(application)

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("🟢 Jarvis do Cerrado operacional.")
    application.run_polling()


if __name__ == "__main__":
    main()
