from typing import Dict
from jarvis.nlp.time_parser import parse_time_command

# =============================================================================
# BASE SEMÂNTICA DE INTENÇÕES (EXTENSÍVEL)
# =============================================================================

INTENT_RULES = {
    "reminder_set": {
        "keywords": [
            "lembra", "lembrete", "me lembra", "me avisa", "avisa",
            "nao deixa eu esquecer", "me recorda", "lembre", "me lembre"
        ]
    },
    "network_scan": {
        "keywords": [
            "quem ta na rede", "quem esta conectado",
            "dispositivos conectados", "quem ta usando internet",
            "quem ta online"
        ]
    },
    "system_status": {
        "keywords": [
            "status da cpu", "uso da cpu", "memoria",
            "ram", "status do sistema", "como ta o sistema", "status"
        ]
    },
    "energy_status": {
        "keywords": [
            "consumo de energia", "energia hoje",
            "energia mensal", "quanto gasta energia"
        ]
    },
    "greet": {
        "keywords": [
            "oi", "ola", "bom dia", "boa tarde", "boa noite"
        ]
    },
    "help": {
        "keywords": [
            "ajuda", "o que voce faz", "comandos",
            "o que da pra fazer"
        ]
    }
}

# =============================================================================
# ENGINE PRINCIPAL
# =============================================================================

def detect_intent(text: str) -> Dict:
    """
    Motor de intenção do Jarvis.
    Recebe TEXTO NORMALIZADO.
    Retorna intenção estruturada.
    """

    if not text or not isinstance(text, str):
        return _fallback()

    text_lower = text.lower()

    # ===============================
    # GREET / HELP (rápido)
    # ===============================
    for intent in ("greet", "help"):
        if _match(intent, text_lower):
            return {"intent": intent}

    # ===============================
    # REMINDER (com parser dedicado)
    # ===============================
    if _match("reminder_set", text_lower):
        return _parse_reminder(text) # Passa texto original (com case) ou lower? time_parser usa lower internamente.

    # ===============================
    # NETWORK
    # ===============================
    if _match("network_scan", text_lower):
        return {"intent": "network_scan"}

    # ===============================
    # SYSTEM
    # ===============================
    if _match("system_status", text_lower):
        return {"intent": "system_status"}

    # ===============================
    # ENERGY (futuro próximo)
    # ===============================
    if _match("energy_status", text_lower):
        return {
            "intent": "energy_status",
            "period": _extract_period(text_lower)
        }

    # ===============================
    # FALLBACK
    # ===============================
    return _fallback()


# =============================================================================
# PARSERS ESPECÍFICOS
# =============================================================================

def _parse_reminder(text: str) -> Dict:
    """
    Parser de lembrete em linguagem natural.
    """

    # Usa o parser temporal aprimorado
    time_data = parse_time_command(text)
    minutes = time_data["minutes"] or 1
    recurrence = time_data["recurrence"]
    is_recurring = time_data["is_recurring"]

    reminder_text = text

    # remove palavras de controle (case insensitive)
    # Aqui fazemos um replace meio bruto, ideal seria regex
    for rule in INTENT_RULES["reminder_set"]["keywords"]:
        # Replace case insensitive é chato em python sem regex, vamos simplificar assumindo texto próximo
        # Para produção melhor usar re.sub(rule, "", text, flags=re.I)
        import re
        reminder_text = re.sub(re.escape(rule), "", reminder_text, flags=re.IGNORECASE)

    # remove tempo explícito (limpeza básica)
    for w in ["minuto", "minutos", "hora", "horas", "a cada", "cada", "todo dia", "todos os dias"]:
        import re
        reminder_text = re.sub(re.escape(w), "", reminder_text, flags=re.IGNORECASE)

    reminder_text = reminder_text.strip()

    # Detecção de ação específica (ex: hidratação)
    action = "default"
    text_lower = text.lower()
    if "agua" in text_lower or "água" in text_lower or "beber" in text_lower:
        action = "hydration"

    return {
        "intent": "reminder_set",
        "action": "create_request", # Changed to create_request to trigger flow
        "text": reminder_text if reminder_text else "Lembrete",
        "params": {
            "text": reminder_text if reminder_text else "Lembrete",
            "minutes": minutes,
            "repeat": is_recurring,
            "recurrence": recurrence,
            "action_type": action
        }
    }


def _extract_period(text: str) -> str:
    """
    Extrai período temporal simples.
    """
    if "hoje" in text:
        return "daily"
    if "mes" in text or "mensal" in text:
        return "monthly"
    if "semana" in text:
        return "weekly"
    return "current"


# =============================================================================
# MATCHER
# =============================================================================

def _match(intent: str, text: str) -> bool:
    for keyword in INTENT_RULES.get(intent, {}).get("keywords", []):
        if keyword in text:
            return True
    return False


# =============================================================================
# FALLBACK
# =============================================================================

def _fallback() -> Dict:
    return {
        "intent": "chat",
        "response": "Uai… pode falar melhor que eu tento entender 😄"
    }
