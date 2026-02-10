from jarvis.core.rules import apply_rules
from jarvis.nlp.intent_engine import detect_intent
from jarvis.core.brain import Brain
from jarvis.core.context import ContextEngine
import re

brain = Brain()

def _extract_entities(text: str):
    entities = {}

    # Listas básicas para suporte a contexto (expansível)
    locations = ["sala", "quarto", "cozinha", "banheiro", "escritorio", "varanda", "garagem"]
    devices = ["luz", "lampada", "ventilador", "ar", "tv", "televisao", "som"]

    for loc in locations:
        if re.search(rf"\b{loc}\b", text, re.IGNORECASE):
            entities["location"] = loc
            break

    for dev in devices:
        if re.search(rf"\b{dev}\b", text, re.IGNORECASE):
            entities["device"] = dev
            break

    return entities

async def route(text: str, chat_id: int = None):
    # 1. Regras Determinísticas (Alta Prioridade & Interrupção de Fluxo)
    rule = apply_rules(text)

    # Se for um comando de gerenciamento, PRIORIZA sobre o fluxo (interrompe o fluxo)
    management_intents = [
        "reminder_list", "reminder_delete", "reminder_update",
        "hydration_control", "hydration_status", "hydration_update", "hydration_activate",
        "hydration_log_explicit" # Note: hydration_log_implicit does NOT interrupt flows
    ]
    if rule and rule["intent"] in management_intents:
        if chat_id:
             # Mata o fluxo silenciosamente para permitir que o comando execute
             ContextEngine.save_context(chat_id, {"flow": None})

        return {
            "intent": rule["intent"],
            "action": rule["action"],
            "entity": rule["entity"],
            "confidence": 1.0,
            "source": "rule",
            "params": rule.get("params", {}),
            "text": text
        }

    # 0. Fluxo Ativo (Prioridade Máxima - salvo exceções acima)
    if chat_id:
        context = ContextEngine.get_context(chat_id)
        if context.get("flow"):
            return {
                "intent": "flow_input",
                "action": "handle_input",
                "entity": None,
                "confidence": 1.0,
                "source": "flow",
                "text": text,
                "params": {"text": text}
            }

    # Processamento normal de Regras (se não for gerenciamento e não tiver fluxo)
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
    if nlp_intent and nlp_intent.get('intent') not in ['chat', 'unknown']:
         # Phase 2: Context Enrichment
         if chat_id:
            context = ContextEngine.get_context(chat_id)

            # Simple Entity Extraction
            current_entities = _extract_entities(text)

            # Se encontrou entidades, usa elas.
            # Se NÃO encontrou, tenta herdar do contexto.
            if current_entities:
                nlp_intent["entities"] = current_entities
            elif context.get("entities"):
                # Herança de contexto (ex: "agora apagar" -> herda "luz da sala")
                nlp_intent["entities"] = context["entities"]
                nlp_intent["context_inherited"] = True

         return nlp_intent

    # 3. IA Generativa (Fallback Cognitivo)
    return await brain.process_intent(text)
