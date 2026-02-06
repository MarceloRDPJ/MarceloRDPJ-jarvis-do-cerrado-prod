from typing import Dict
from rapidfuzz import process, fuzz
import re
from jarvis.nlp.time_parser import parse_time_command

# =============================================================================
# ENGINE HÍBRIDO (PHASE 1)
# =============================================================================

class HybridIntentEngine:
    def __init__(self):
        self.intent_patterns = {
            "reminder_set": [
                "lembra", "lembrete", "me lembra", "me avisa", "avisa",
                "nao deixa eu esquecer", "me recorda", "lembre", "me lembre",
                "lembrar de beber agua", "avisa a cada minuto", "criar lembrete"
            ],
            "reminder_list": [
                "listar lembretes", "ver meus lembretes", "quais sao meus lembretes",
                "ver avisos", "mostrar lembretes", "lista de tarefas", "o que tenho pra hoje"
            ],
            "reminder_delete": [
                "cancelar lembrete", "apagar lembrete", "remover aviso",
                "deleta esse lembrete", "esquecer lembrete", "excluir tarefa"
            ],
            "network_scan": [
                "quem ta na rede", "quem esta conectado",
                "dispositivos conectados", "quem ta usando internet",
                "quem ta online", "verificar rede", "scan de rede"
            ],
            "network_rename": [
                "mudar o nome do", "renomear dispositivo", "chamar o dispositivo",
                "apelidar o ip", "alterar nome na rede", "editar o nome da", "editar nome"
            ],
            "hydration_status": [
                "quantas aguas eu ja bebi", "status hidratacao", "meta de agua",
                "quanto eu bebi hoje", "contagem de agua"
            ],
            "hydration_log": [
                "bebi", "tomei agua", "mais um copo", "bebi agua", "tomei mais uma",
                "registra agua", "anota ai bebi"
            ],
            "system_status": [
                "status da cpu", "uso da cpu", "memoria",
                "ram", "status do sistema", "como ta o sistema", "status",
                "tudo bem", "como você está", "saúde do sistema"
            ],
            "energy_status": [
                "consumo de energia", "energia hoje",
                "energia mensal", "quanto gasta energia"
            ],
            "greet": [
                "oi", "ola", "bom dia", "boa tarde", "boa noite", "e ai"
            ],
            "small_talk": [
                "kk", "uai", "aham", "to bebendo", "boa"
            ],
            "identity_who": [
                "quem é você", "quem e voce", "qual seu nome"
            ],
            "identity_capabilities": [
                "o que voce sabe fazer", "o que voce faz", "quais seus poderes",
                "me ajuda com o que"
            ],
            "help": [
                "ajuda", "comandos", "menu", "opcoes", "socorro"
            ],
            "light_on": [
                "ligar a luz", "acender luz", "acenda a luz da sala", "ligar", "acender",
                "ligar a luz da sala", "ligar a luz do quarto", "ligar a luz da cozinha"
            ],
            "light_off": [
                "apagar luz", "desligar a luz", "apague a luz do quarto", "apagar", "desligar",
                "apagar a luz da sala", "apagar a luz do quarto", "apagar a luz da cozinha"
            ],
        }
        self.similarity_threshold = 88

    def identify_intent(self, user_input: str) -> Dict:
        if not user_input or not isinstance(user_input, str):
             return {"intent": "unknown", "confidence": 0.0}

        best_intent = "unknown"
        best_score = 0

        for intent, examples in self.intent_patterns.items():
            # WRatio handles partial matches and casing better
            match_result = process.extractOne(user_input, examples, scorer=fuzz.WRatio, score_cutoff=self.similarity_threshold)
            if match_result:
                match, score, _ = match_result
                if score > best_score:
                    best_score = score
                    best_intent = intent

        if best_score >= self.similarity_threshold:
            return {"intent": best_intent, "confidence": best_score / 100.0}

        return {"intent": "unknown", "confidence": 0.0}

# Global instance
engine = HybridIntentEngine()

def detect_intent(text: str) -> Dict:
    """
    Detecta intenção usando similaridade (RapidFuzz).
    Mantém compatibilidade com chamadas existentes.
    """
    result = engine.identify_intent(text)
    intent = result["intent"]

    if intent == "unknown":
        return _fallback()

    if intent == "reminder_set":
        return _parse_reminder(text)

    if intent == "energy_status":
        return {
            "intent": "energy_status",
            "period": _extract_period(text.lower())
        }

    if intent == "network_rename":
        return _parse_rename(text)

    if intent == "hydration_log":
        return {"intent": "hydration_log"}

    if intent == "reminder_list":
        return {"intent": "reminder_list"}

    if intent == "reminder_delete":
        # Tenta extrair ID ou termo de busca
        import re
        match = re.search(r'(\d+)', text)
        target_id = int(match.group(1)) if match else None
        return {
            "intent": "reminder_delete",
            "target_id": target_id,
            "text": text
        }

    return result

# =============================================================================
# PARSERS ESPECÍFICOS
# =============================================================================

def _parse_rename(text: str) -> Dict:
    """
    Extrai IP/MAC e novo nome.
    Ex: "mudar o nome do 192.168.1.52 para PC marcelo"
    """
    import re
    # Extract IP
    ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', text)
    target = ip_match.group(1) if ip_match else None

    # Extract Name (simple heuristic: everything after "para" or "de")
    name = None
    if target:
        # Tenta pegar tudo depois de "para" ou "de"
        # Melhorar regex para pegar nome composto até o fim da string
        match = re.search(r'(?:para|de)\s+(.+)$', text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()

    return {
        "intent": "network_rename",
        "action": "rename",
        "target": target,
        "name": name,
        "text": text,
        "params": { # Ensure params are populated for Executor
            "target": target,
            "name": name,
            "text": text
        }
    }

def _parse_reminder(text: str) -> Dict:
    """
    Parser de lembrete em linguagem natural.
    """
    # Usa o parser temporal aprimorado
    time_data = parse_time_command(text)
    # Permite 0 para forçar clarificação se o tempo for ambíguo
    minutes = time_data["minutes"]
    recurrence = time_data["recurrence"]
    is_recurring = time_data["is_recurring"]

    reminder_text = text

    # Remove palavras-chave da intenção para limpar o texto
    # Usa a lista do engine para garantir consistência
    keywords = engine.intent_patterns["reminder_set"]

    # Ordena por tamanho decrescente para remover frases longas primeiro
    sorted_keywords = sorted(keywords, key=len, reverse=True)

    for rule in sorted_keywords:
        if rule in reminder_text.lower():
             # Replace case insensitive simples para termos exatos
             reminder_text = re.sub(re.escape(rule), "", reminder_text, flags=re.IGNORECASE)

    # Remove termos de tempo explícitos
    for w in ["minuto", "minutos", "hora", "horas", "a cada", "cada", "todo dia", "todos os dias"]:
        reminder_text = re.sub(re.escape(w), "", reminder_text, flags=re.IGNORECASE)

    reminder_text = reminder_text.strip()
    # Limpeza extra de pontuação/espaços duplicados
    reminder_text = re.sub(r'\s+', ' ', reminder_text).strip(' .,-')

    action = "default"
    text_lower = text.lower()
    if "agua" in text_lower or "água" in text_lower or "beber" in text_lower:
        action = "hydration"

    return {
        "intent": "reminder_set",
        "action": "create_request",
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
    if "hoje" in text:
        return "daily"
    if "mes" in text or "mensal" in text:
        return "monthly"
    if "semana" in text:
        return "weekly"
    return "current"

def _fallback() -> Dict:
    return {
        "intent": "chat",
        "response": "Uai… pode falar melhor que eu tento entender 😄"
    }
