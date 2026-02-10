import logging
from datetime import datetime, timedelta, timezone
from jarvis.database.persistence import Persistence

logger = logging.getLogger("core.reminder_callbacks")

class ReminderCallbacks:
    """Handlers para callbacks de lembretes"""

    @staticmethod
    async def handle_done(task_id: int, chat_id: int, bot):
        """Marca lembrete como concluído"""
        Persistence.update_task_status(task_id, 'completed')

        await bot.send_message(
            chat_id=chat_id,
            text="✅ Lembrete marcado como concluído!"
        )

        logger.info(f"Lembrete {task_id} concluído pelo usuário")

    @staticmethod
    async def handle_snooze(task_id: int, chat_id: int, minutes: int, bot):
        """Adia lembrete por X minutos"""
        new_time = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        Persistence.update_task_next_run(task_id, new_time)

        await bot.send_message(
            chat_id=chat_id,
            text=f"⏰ Lembrete adiado por {minutes} minutos."
        )

        logger.info(f"Lembrete {task_id} adiado por {minutes}min")

    @staticmethod
    async def handle_cancel(task_id: int, chat_id: int, bot):
        """Cancela lembrete definitivamente"""
        Persistence.update_task_status(task_id, 'cancelled')

        await bot.send_message(
            chat_id=chat_id,
            text="🗑️ Lembrete cancelado."
        )

        logger.info(f"Lembrete {task_id} cancelado pelo usuário")
