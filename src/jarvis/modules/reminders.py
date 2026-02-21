import logging
import json
from datetime import datetime
from typing import Dict, Any
from jarvis.config import Config
try:
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:
    pass

logger = logging.getLogger("modules.reminders")

# ===============================
# FUNÇÕES DE MENSAGEM (PERSONALIDADE)
# ===============================
def get_reminder_message(task: Dict[str, Any], now: datetime) -> str:
    """
    Gera a mensagem do lembrete com base no horário e tipo.
    """
    text = task['text']
    meta = json.loads(task['meta'] or '{}')

    # Horário local via Config
    local_now = now.astimezone(Config.TZ)
    hour = local_now.hour

    is_madrugada = 23 <= hour or hour < 6
    is_dia = 6 <= hour < 18
    is_noite = 18 <= hour < 23

    # Hidratação
    if task.get('action') == 'hydration':
        return _get_hydration_message(text, meta, is_madrugada, is_dia)

    # Genérico
    if is_madrugada:
        return f"🌙 {text}"

    if is_dia:
        return f"⏰ {text}"

    return f"⏰ Lembrete: {text}"

def _get_hydration_message(text: str, meta: Dict, is_madrugada: bool, is_dia: bool) -> str:
    if is_madrugada:
        return f"🌙 Hora de beber água."

    if is_dia:
        cup = meta.get('cup_ml', 250)
        return f"💧 Hora de beber água ({cup}ml). Bora manter o ritmo."

    return f"💧 Lembrete de hidratação."

async def send_reminder(app, task_id: int, chat_id: int, message_text: str):
    """
    Envia o lembrete com botões interativos (Snooze, Done, Cancel).
    """
    try:
        # Criar botões de ação
        keyboard = [
            [
                InlineKeyboardButton("✅ Feito", callback_data=f"rem_done_{task_id}"),
                InlineKeyboardButton("⏰ +15min", callback_data=f"rem_snooze_{task_id}_15"),
            ],
            [
                InlineKeyboardButton("⏰ +1h", callback_data=f"rem_snooze_{task_id}_60"),
                InlineKeyboardButton("❌ Cancelar", callback_data=f"rem_cancel_{task_id}"),
            ]
        ]

        await app.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"Lembrete {task_id} enviado para {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Falha ao enviar lembrete {task_id}: {e}")
        return False
