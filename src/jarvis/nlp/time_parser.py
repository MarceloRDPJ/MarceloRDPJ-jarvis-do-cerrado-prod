import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from jarvis.config import Config

WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

def format_pt_br(dt: datetime) -> str:
    """Formata data para português amigável: Sábado, 08/02 às 14h30"""
    wd = WEEKDAYS[dt.weekday()]
    date_str = dt.strftime("%d/%m")
    time_str = dt.strftime("%Hh%M").replace("00", "") # 14h00 -> 14h
    if time_str.endswith("h"): time_str = time_str # 14h

    return f"{wd}, {date_str} às {time_str}"

def parse_time_command(text: str) -> Dict[str, Any]:
    """
    Extrai informações temporais ricas de frases humanas.
    Retorna:
    {
        "minutes": int (intervalo em minutos),
        "target_date": datetime (objeto datetime absoluto),
        "formatted": str (string amigável para confirmação),
        "recurrence": str ("daily", "weekly", "none"),
        "is_recurring": bool
    }
    """
    result = {
        "minutes": 0,
        "target_date": None,
        "formatted": None,
        "recurrence": "none",
        "is_recurring": False,
        "interval_minutes": 0,
    }

    text = text.lower()
    now = datetime.now(Config.TZ)

    # Recorrência explícita
    if "todo dia" in text or "todos os dias" in text or "diariamente" in text:
        result["recurrence"] = "daily"
        result["is_recurring"] = True
        result["interval_minutes"] = 1440
    elif "semanal" in text or "toda semana" in text:
        result["recurrence"] = "weekly"
        result["is_recurring"] = True
        result["interval_minutes"] = 10080
    elif "a cada" in text:
        # "a cada" implica recorrência, mesmo que seja intraday
        result["is_recurring"] = True

    # 1. Extração de intervalo RELATIVO (minutos/horas)
    # Ex: "a cada 10 minutos", "daqui 2 horas"
    relative_minutes = 0
    hours_match = re.search(r"(\d+)\s*(?:hora|horas|h)(?!\s*\d)", text) # Fix: avoid matching part of 12h30
    if hours_match:
        relative_minutes += int(hours_match.group(1)) * 60

    minutes_match = re.search(r"(\d+)\s*(?:minuto|minutos|min)", text)
    if minutes_match:
        relative_minutes += int(minutes_match.group(1))

    if relative_minutes > 0:
        result["minutes"] = relative_minutes
        result["target_date"] = now + timedelta(minutes=relative_minutes)
        result["formatted"] = format_pt_br(result["target_date"])
        if "a cada" in text:
            result["interval_minutes"] = relative_minutes

        # Se tem intervalo relativo e "a cada", já está resolvido
        if result["is_recurring"] or "daqui" in text:
             return result

    # 2. Extração de Dia da Semana (ABSOLUTO/FUTURO)
    # Ex: "no sabado", "terça feira"
    days_map = {
        "domingo": 6, "segunda": 0, "terca": 1, "terça": 1,
        "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "sábado": 5
    }

    target_weekday = None
    for day, idx in days_map.items():
        if day in text:
            target_weekday = idx
            break

    # Tratamento para "amanhã"
    if "amanha" in text or "amanhã" in text:
        target_weekday = (now.weekday() + 1) % 7
        # Force logic below to handle day shift

    # 3. Extração de Horário Específico
    # Ex: "as 12h", "14:30", "meio dia"
    target_hour = None
    target_minute = 0

    time_match = re.search(r"(?:as|às)\s+(\d{1,2})(?:h|:)?(\d{2})?", text)
    if not time_match:
        time_match = re.search(r"(\d{1,2}):(\d{2})", text)

    if time_match:
        target_hour = int(time_match.group(1))
        target_minute = int(time_match.group(2)) if time_match.group(2) else 0
    elif "meio dia" in text:
        target_hour = 12
    elif "meia noite" in text:
        target_hour = 0

    # 4. Cálculo de Delta (Minutos até o alvo)
    if target_weekday is not None or target_hour is not None:
        target_date = now

        # Ajuste de Dia
        if target_weekday is not None:
            days_ahead = target_weekday - now.weekday()
            if days_ahead <= 0: # Target day already happened this week
                days_ahead += 7
            target_date += timedelta(days=days_ahead)
        elif "amanha" in text or "amanhã" in text: # Redundant check but safe
             target_date += timedelta(days=1)

        # Ajuste de Hora
        # REGRA DE OURO: Se o usuário NÃO especificou hora, NÃO assumir.
        # Retornar 0 minutos para forçar clarificação.
        if target_hour is None:
            # Se não tem hora, é ambíguo.
            result["minutes"] = 0
            # Mas podemos retornar o dia, caso queira
            # result["target_date"] = target_date.replace(hour=9, minute=0) # NÃO! Sem assumptions.
            return result

        target_date = target_date.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

        # Se for hoje mas a hora já passou, move pro próximo (se não tiver dia da semana fixo e nem for amanhã)
        if target_weekday is None and "amanha" not in text and "amanhã" not in text and target_date < now:
            target_date += timedelta(days=1)

        delta = target_date - now
        result["minutes"] = int(delta.total_seconds() / 60)
        result["target_date"] = target_date
        result["formatted"] = format_pt_br(target_date)

        # Se tem dia da semana, pode ser recorrência semanal
        if target_weekday is not None and "vez" not in text: # "1 vez" nega recorrência
             pass # Por enquanto tratamos como one-shot se não tiver "toda semana"

    # Fallback para "daqui a pouco" -> 15 min
    if result["minutes"] == 0 and "daqui a pouco" in text:
        result["minutes"] = 15
        result["target_date"] = now + timedelta(minutes=15)
        result["formatted"] = format_pt_br(result["target_date"])

    # 🚫 REGRA DE OURO: Sem default silencioso.
    # Se minutes é 0, retorna 0 explicitamente para que o fluxo pergunte.

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
