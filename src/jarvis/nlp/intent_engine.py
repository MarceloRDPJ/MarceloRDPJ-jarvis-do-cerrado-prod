from typing import Dict
from jarvis.nlp.time_parser import parse_minutes, is_recurrent

# =============================================================================
# BASE SEMÂNTICA DE INTENÇÕES (EXTENSÍVEL)
# =============================================================================

INTENT_RULES = {
    "reminder_set": {
        "keywords": [
            "lembra", "lembrete", "me lembra", "me avisa", "avisa",
            "nao deixa eu esquecer", "me recorda"
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
            "ram", "status do sistema", "como ta o sistema"
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

    # ===============================
    # GREET / HELP (rápido)
    # ===============================
    for intent in ("greet", "help"):
        if _match(intent, text):
            return {"intent": intent}

    # ===============================
    # REMINDER (com parser dedicado)
    # ===============================
    if _match("reminder_set", text):
        return _parse_reminder(text)

    # ===============================
    # NETWORK
    # ===============================
    if _match("network_scan", text):
        return {"intent": "network_scan"}

    # ===============================
    # SYSTEM
    # ===============================
    if _match("system_status", text):
        return {"intent": "system_status"}

    # ===============================
    # ENERGY (futuro próximo)
    # ===============================
    if _match("energy_status", text):
        return {
            "intent": "energy_status",
            "period": _extract_period(text)
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

    minutes = parse_minutes(text) or 1
    repeat = is_recurrent(text)

    reminder_text = text

    # remove palavras de controle
    for rule in INTENT_RULES["reminder_set"]["keywords"]:
        reminder_text = reminder_text.replace(rule, "")

    # remove tempo explícito
    reminder_text = reminder_text.replace(str(minutes), "")
    for w in ["minuto", "minutos", "hora", "horas", "a cada", "cada"]:
        reminder_text = reminder_text.replace(w, "")

    reminder_text = reminder_text.strip()

    return {
        "intent": "reminder_set",
        "action": "create",
        "text": reminder_text if reminder_text else "Lembrete",
        "minutes": minutes,
        "repeat": repeat
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
