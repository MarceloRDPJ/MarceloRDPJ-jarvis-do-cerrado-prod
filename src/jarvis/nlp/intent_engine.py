from typing import Dict
from rapidfuzz import process, fuzz
import re
from jarvis.nlp.time_parser import parse_time_command
from jarvis.config import Config

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
                "quem ta online", "verificar rede", "scan de rede",
                "scanear", "escanear", "escaniar", "scan", "ver rede"
            ],
            "network_status": [
                "status da internet", "internet ta on", "ping", "conexao",
                "internet caiu", "internet ta ruim", "tem internet",
                "monitorar internet", "verificar conexao", "status da rede",
                "estado da rede", "rede ta funcionando"
            ],
            "network_speed": [
                "velocidade da internet", "speedtest", "teste de velocidade",
                "internet ta lenta", "medir velocidade", "taxa de download"
            ],
            "network_stats": [
                "estatisticas de rede", "stats adguard", "consumo de rede",
                "quem ta gastando internet", "top consumidores", "bloqueios adguard",
                "uso do adguard"
            ],
            "network_block_device": [
                "bloquear dispositivo", "bloquear ip", "cortar internet do",
                "bloqueia o ip", "travar internet"
            ],
            "network_block_site": [
                "bloquear site", "bloquear dominio", "bloqueia o site",
                "proibir site", "nao deixar acessar"
            ],
            "network_rename": [
                "mudar o nome do", "renomear", "renomear dispositivo", "chamar o dispositivo",
                "apelidar o ip", "alterar nome na rede", "editar o nome da", "editar nome",
                "mudar nome de", "trocar nome"
            ],
            "hydration_status": [
                "quantas aguas eu ja bebi", "status hidratacao", "meta de agua",
                "quanto eu bebi hoje", "contagem de agua"
            ],
            "hydration_log": [
                "bebi", "tomei agua", "mais um copo", "bebi agua", "tomei mais uma",
                "registra agua", "anota ai bebi"
            ],
            "hydration_analytics": [
                "analise de hidratacao", "padroes de agua", "insights agua",
                "estatisticas agua", "como tenho bebido agua", "historico de agua"
            ],
            "system_status": [
                "status da cpu", "uso da cpu", "memoria",
                "ram", "status do sistema", "como ta o sistema", "status",
                "tudo bem", "como você está", "saúde do sistema"
            ],
            "fan_control": [
                "ligar fan", "desligar fan", "status do fan", "ventoinha",
                "ligar ventoinha", "desligar ventoinha", "controlar fan",
                "cooler"
            ],
            "system_logs": [
                "logs do sistema", "ver logs", "log de erro", "mostrar logs", "ultimos eventos"
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
            # COMMAND LIST INTENT
            "command_list": [
                "lista de comandos", "todos os comandos", "lista comandos", "manual",
                "quais seus comandos", "o que posso falar", "comandos disponiveis"
            ],
            "light_on": [
                "ligar a luz", "acender luz", "acenda a luz da sala", "ligar", "acender",
                "ligar a luz da sala", "ligar a luz do quarto", "ligar a luz da cozinha"
            ],
            "light_off": [
                "apagar luz", "desligar a luz", "apague a luz do quarto", "apagar", "desligar",
                "apagar a luz da sala", "apagar a luz do quarto", "apagar a luz da cozinha"
            ],

            # ===== WAKE-ON-LAN (WOL) =====
            "wake_pc": [
                # Comandos diretos
                "ligar o pc",
                "ligar pc",
                "ligar computador",
                "ligar o computador",

                # Variações com "acordar"
                "acordar o pc",
                "acordar pc",
                "acordar computador",

                # Wake on LAN explícito
                "wake on lan",
                "wol",
                "wake pc",

                # Comandos naturais
                "liga o pc pra mim",
                "acorda o pc",
                "preciso que ligue o pc",
                "pode ligar o computador",

                # Com urgência
                "liga o pc agora",
                "liga o pc urgente",

                # Variações regionais (goiano)
                "bota o pc pra funcionar",
                "liga esse trem ai",  # (se referindo ao PC)
            ],

            "pc_status": [
                "pc ta ligado",
                "pc esta ligado",
                "computador ta on",
                "pc ta online",
                "pc respondendo",
            ],

            # NOVOS INTENTS DE IDENTIDADE
            "identity_creator": [
                "quem te criou", "quem fez voce", "quem é seu criador",
                "quem programou voce", "quem desenvolveu voce",
                "quem é seu pai", "quem te fez", "quem é marcelo", "conhece o marcelo"
            ],
            "identity_purpose": [
                "qual seu proposito", "pra que voce serve", "qual sua missao",
                "por que voce existe", "qual seu objetivo"
            ],
            "identity_tech": [
                "como voce funciona", "qual sua tecnologia", "como foi feito",
                "qual sua stack", "que linguagem voce usa"
            ],
            # NOVOS INTENTS DE MENU
            "menu_rede": ["menu rede", "comandos rede", "ajuda rede", "menu_rede"],
            "menu_agenda": ["menu agenda", "comandos lembretes", "ajuda lembretes", "menu_agenda"],
            "menu_automacoes": ["menu automacoes", "menu_automacoes"],
            "menu_sistema": ["menu sistema", "comandos sistema", "ajuda sistema", "menu_sistema"],

            # AUTOMATION SPECIFICS
            "automation_list": ["listar automacoes", "ver automacoes", "automacoes ativas", "quais automacoes"],
            "automation_config": ["config automacoes", "configurar automacoes", "editar automacoes"]
        }
        self.similarity_threshold = int(Config.INTENT_CONFIDENCE_THRESHOLD * 100)

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

    if intent == "hydration_analytics":
        return {"intent": "hydration_analytics"}

    if intent == "reminder_list":
        return {"intent": "reminder_list"}

    if intent == "network_status":
        return {"intent": "network_status", "action": "check", "entity": "network"}

    if intent == "network_speed":
        return {"intent": "network_speed", "action": "check", "entity": "network"}

    if intent == "network_stats":
        return {"intent": "network_stats"}

    if intent == "network_block_device":
        # Extract IP
        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', text)
        ip = ip_match.group(1) if ip_match else None
        return {"intent": "network_block_device", "params": {"ip": ip, "target": ip}}

    if intent == "network_block_site":
        # Extract Domain (simplistic)
        # remove "bloquear", "site", etc.
        clean = text.lower()
        for w in ["bloquear", "site", "acesso", "ao", "o", "a", "bloqueia"]:
            clean = clean.replace(w, "")
        domain = clean.strip()
        return {"intent": "network_block_site", "params": {"site": domain, "domain": domain}}

    if intent == "reminder_delete":
        # Tenta extrair ID ou termo de busca
        import re
        match = re.search(r'(\d+)', text)
        target_id = int(match.group(1)) if match else None
        return {
            "intent": "reminder_delete",
            "text": text,
            "params": {"target_id": target_id} # Fixed: put in params for executor
        }

    if intent == "command_list":
        return {"intent": "command_list"}

    return result

# =============================================================================
# PARSERS ESPECÍFICOS
# =============================================================================

def _parse_rename(text: str) -> Dict:
    """
    Extrai IP/MAC e novo nome.
    Ex: "mudar o nome do 192.168.1.52 para PC marcelo"
    Ex: "renomear 192.168.1.54 por celular Marcelo"
    """
    import re
    # Extract IP
    ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', text)
    target = ip_match.group(1) if ip_match else None

    # Extract Name
    name = None
    if target:
        # Regex mais flexível para capturar o nome após preposições
        # Captura tudo após 'para', 'por', 'de', ou logo após o IP se não houver preposição
        # Ex: "renomear X para Y" -> Y
        # Ex: "renomear X por Y" -> Y
        # Ex: "renomear X de Y" -> Y (menos comum mas possível)
        match = re.search(r'(?:para|por|de)\s+(.+)$', text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
        else:
            # Fallback: Se não tem preposição, pega o que vem depois do IP
            parts = text.split(target)
            if len(parts) > 1:
                potential = parts[1].strip()
                if potential:
                    name = potential

    return {
        "intent": "network_rename",
        "action": "rename",
        "target": target,
        "name": name,
        "text": text,
        "params": {
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
    minutes = time_data["minutes"]
    recurrence = time_data["recurrence"]
    is_recurring = time_data["is_recurring"]
    target_date = time_data.get("target_date")

    reminder_text = text

    # 1. Remove palavras-chave da intenção
    keywords = engine.intent_patterns["reminder_set"]
    sorted_keywords = sorted(keywords, key=len, reverse=True)

    for rule in sorted_keywords:
        if rule in reminder_text.lower():
             reminder_text = re.sub(re.escape(rule), "", reminder_text, flags=re.IGNORECASE)

    # 2. Remove expressões de tempo (Cleaning agressivo)
    # Dias da semana
    weekdays = ["domingo", "segunda", "segunda-feira", "terca", "terça", "terça-feira", "quarta", "quarta-feira", "quinta", "quinta-feira", "sexta", "sexta-feira", "sabado", "sábado"]
    for day in weekdays:
        reminder_text = re.sub(rf"\b(?:no|na|em)?\s*{day}\b", "", reminder_text, flags=re.IGNORECASE)

    # Hoje/Amanhã/Daqui
    reminder_text = re.sub(r"\b(hoje|amanha|amanhã)\b", "", reminder_text, flags=re.IGNORECASE)
    reminder_text = re.sub(r"\bdaqui a pouco\b", "", reminder_text, flags=re.IGNORECASE)
    reminder_text = re.sub(r"\bdaqui (?:a )?[\d]+ (?:minutos|min|horas|h)\b", "", reminder_text, flags=re.IGNORECASE)

    # Horários (às 14h, 12:30, etc)
    reminder_text = re.sub(r"\b(?:as|às|ás)\s+\d{1,2}(?:[:h]\d{2})?h?\b", "", reminder_text, flags=re.IGNORECASE)
    reminder_text = re.sub(r"\b\d{1,2}:\d{2}\b", "", reminder_text, flags=re.IGNORECASE)

    # Termos soltos
    for w in ["minuto", "minutos", "hora", "horas", "a cada", "cada", "todo dia", "todos os dias"]:
        reminder_text = re.sub(re.escape(w), "", reminder_text, flags=re.IGNORECASE)

    # Limpeza final
    reminder_text = reminder_text.strip()
    # Remove preposições de ligação que sobraram no início (ex: "de puxar" -> "puxar")
    reminder_text = re.sub(r"^(?:de|pra|que|o|a)\s+", "", reminder_text, flags=re.IGNORECASE)

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
            "target_date": target_date,
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
