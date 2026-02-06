from core.rules import apply_rules
from core.brain import Brain

brain = Brain()

async def route(text: str):
    rule = apply_rules(text)
    if rule:
        return {
            "intent": rule["intent"],
            "action": rule["action"],
            "entity": rule["entity"],
            "confidence": 1.0,
            "source": "rule"
        }

    # Só aqui entra IA
    return await brain.process_intent(text)
