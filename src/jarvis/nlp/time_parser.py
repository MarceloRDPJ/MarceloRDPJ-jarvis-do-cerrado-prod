import re
from typing import Dict, Any, Optional

def parse_time_command(text: str) -> Dict[str, Any]:
    """
    Extrai informações temporais ricas de frases humanas.
    Retorna:
    {
        "minutes": int (intervalo em minutos),
        "recurrence": str ("daily", "weekly", "none"),
        "is_recurring": bool
    }
    """
    result = {
        "minutes": 0,
        "recurrence": "none",
        "is_recurring": False
    }

    text = text.lower()

    # Recorrência explícita
    if "todo dia" in text or "todos os dias" in text or "diariamente" in text:
        result["recurrence"] = "daily"
        result["is_recurring"] = True
    elif "semanal" in text or "toda semana" in text:
        result["recurrence"] = "weekly"
        result["is_recurring"] = True
    elif "a cada" in text:
        # "a cada" implica recorrência, mesmo que seja intraday
        result["is_recurring"] = True

    # Extração de intervalo (minutos/horas)
    # Ex: "a cada 10 minutos", "daqui 2 horas"

    # Horas
    hours_match = re.search(r"(\d+)\s*(?:hora|horas|h)", text)
    if hours_match:
        result["minutes"] += int(hours_match.group(1)) * 60

    # Minutos
    minutes_match = re.search(r"(\d+)\s*(?:minuto|minutos|min)", text)
    if minutes_match:
        result["minutes"] += int(minutes_match.group(1))

    # Fallback para "daqui a pouco" -> 15 min (exemplo de regra de negócio suave)
    if result["minutes"] == 0 and "daqui a pouco" in text:
        result["minutes"] = 15

    return result

def parse_minutes(text: str) -> Optional[int]:
    """
    Mantido para retrocompatibilidade, mas recomenda-se usar parse_time_command.
    """
    data = parse_time_command(text)
    return data["minutes"] if data["minutes"] > 0 else None

def is_recurrent(text: str) -> bool:
    data = parse_time_command(text)
    return data["is_recurring"]
