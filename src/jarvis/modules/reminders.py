import logging
import json
from datetime import datetime
from typing import Dict, Any
from jarvis.config import Config

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
    prefix = "⏰"
    priority = meta.get("priority", "normal")
    if priority == "urgent":
        prefix = "🚨 URGENTE"
    elif priority == "high":
        prefix = "⚠️ IMPORTANTE"

    category = meta.get("category")
    suffix = f"\n🏷️ {category}" if category else ""

    if is_madrugada:
        return f"🌙 {text}{suffix}"

    if is_dia:
        return f"{prefix} {text}{suffix}"

    return f"{prefix} Lembrete: {text}{suffix}"

def _get_hydration_message(text: str, meta: Dict, is_madrugada: bool, is_dia: bool) -> str:
    if is_madrugada:
        return f"🌙 Hora de beber água."

    if is_dia:
        cup = meta.get('cup_ml', 250)
        return f"💧 Hora de beber água ({cup}ml). Bora manter o ritmo."

    return f"💧 Lembrete de hidratação."
