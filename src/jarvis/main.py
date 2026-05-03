import logging
import asyncio
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
from jarvis.core.brain import Brain
from jarvis.core.executor import Executor
from jarvis.core import router
from jarvis.database.persistence import Persistence
from jarvis.core.events import Event

from jarvis.services.collector import CollectorService
from jarvis.services.scheduler import SchedulerService
from jarvis.services.guardian import GuardianService
from jarvis.services.fan_control import FanControlService

# =====================================================
# LOGGING
# =====================================================
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
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

        parts = text.split("_")
        action = parts[1]  # done, snooze, cancel
        task_id = int(parts[2])

        if action == "done":
            await ReminderCallbacks.handle_done(task_id, chat_id, context.bot)
            return

        elif action == "snooze":
            minutes = int(parts[3])
            await ReminderCallbacks.handle_snooze(task_id, chat_id, minutes, context.bot)
            return

        elif action == "cancel":
            await ReminderCallbacks.handle_cancel(task_id, chat_id, context.bot)
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
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("🟢 Jarvis do Cerrado operacional.")
    application.run_polling()


if __name__ == "__main__":
    main()
