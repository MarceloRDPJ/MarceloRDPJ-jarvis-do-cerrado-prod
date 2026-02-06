from jarvis.core.rules import apply_rules
from jarvis.nlp.intent_engine import detect_intent
from jarvis.core.brain import Brain

brain = Brain()

async def route(text: str):
    # 1. Regras Determinísticas (Alta Prioridade)
    rule = apply_rules(text)
    if rule:
        # Se a regra for um lembrete simples, deixamos o NLP lidar para extrair tempo
        # A menos que seja um comando muito específico
        if rule['intent'] == 'reminder_set' and rule.get('action') == 'create':
            pass # Deixa passar para o NLP
        else:
            return {
                "intent": rule["intent"],
                "action": rule["action"],
                "entity": rule["entity"],
                "confidence": 1.0,
                "source": "rule",
                "params": rule.get("params", {}),
                "text": text # Garante que o texto original seja passado
            }

    # 2. NLP Local (Intent Engine)
    nlp_intent = detect_intent(text)
    if nlp_intent and nlp_intent['intent'] != 'chat':
         # Se o NLP detectou algo específico (não fallback)
         return nlp_intent

    # 3. IA Generativa (Fallback Cognitivo)
    return await brain.process_intent(text)
