import unicodedata
import re
from typing import Dict, List

# =============================================================================
# BASE DE NORMALIZAÇÃO LINGUÍSTICA (ENTERPRISE / DETERMINÍSTICA)
# =============================================================================
# ⚠️ Normaliza linguagem, NÃO semântica, NÃO intenção
REPLACEMENTS: Dict[str, str] = {
    # --- Abreviações & Gírias ---
    "vc": "voce", "vcs": "voces",
    "tb": "tambem", "tbm": "tambem",
    "obg": "obrigado", "obgr": "obrigado",
    "vlw": "valeu", "flw": "falou",
    "pq": "porque", "q": "que", "qe": "que",
    "qdo": "quando", "qaundo": "quando",
    "mto": "muito", "mt": "muito",
    "tava": "estava", "ta": "esta", "to": "estou",
    "eh": "e", "blz": "beleza",
    "vdd": "verdade", "ctz": "certeza",
    "fds": "fim de semana",
    "msg": "mensagem",
    "cmg": "comigo", "ctgo": "contigo",
    "p": "para", "pra": "para",
    "pro": "para o", "pras": "para as", "pros": "para os",
    "td": "tudo", "tmj": "tamojunto",
    "agr": "agora", "hj": "hoje",
    "pfv": "por favor", "plis": "por favor",
    "gnt": "gente", "ngm": "ninguem",
    "tlg": "ta ligado",

    # --- Ortografia Comum ---
    "concerteza": "com certeza",
    "comcerteza": "com certeza",
    "excessao": "excecao",
    "geito": "jeito",
    "paralizar": "paralisar",
    "analizar": "analisar",
    "atraz": "atras",
    "mecher": "mexer",
    "ancioso": "ansioso",

    # --- Unidades ---
    "h": "hora", "hs": "horas", "hr": "hora", "hrs": "horas",
    "min": "minuto", "mins": "minutos",
    "seg": "segundo", "segs": "segundos",
    "kg": "quilograma", "g": "grama",
    "km": "quilometro", "m": "metro",
    "cm": "centimetro", "l": "litro", "ml": "mililitro",
}

# =============================================================================
# REGEX PRÉ-COMPILADAS (PERFORMANCE RASPI)
# =============================================================================
RE_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
RE_EMAIL = re.compile(r"\b\S+@\S+\.\S+\b")
RE_LAUGHTER = re.compile(
    r"\b(k{2,}|(ha){2,}|(he){2,}|(rs){2,}|(ah){2,})\b",
    re.IGNORECASE
)
RE_NON_ALPHANUMERIC = re.compile(r"[^\w\s\[\]]")
RE_EXTRA_SPACES = re.compile(r"\s+")
RE_REPEATED_CHARS = re.compile(r"(.)\1{2,}")
RE_NUM_LETTER = re.compile(r"(\d)([a-zA-Z])|([a-zA-Z])(\d)")

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================
def remove_accents(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )

def reduce_lengthened_words(text: str) -> str:
    """
    Reduz exagero emocional mantendo sinal humano.
    Ex: 'oooiiiii' -> 'ooii'
    """
    return RE_REPEATED_CHARS.sub(r"\1\1", text)

# =============================================================================
# NORMALIZADOR PRINCIPAL
# =============================================================================
def normalize_text(text: str) -> str:
    """
    Normalizador de Linguagem Natural – Jarvis do Cerrado

    ✔ determinístico
    ✔ preserva emoção
    ✔ pronto para NLP, Intent Engine e Context Awareness
    """

    if not isinstance(text, str) or not text.strip():
        return ""

    # 1. Proteção de dados sensíveis
    text = RE_URL.sub(" [url] ", text)
    text = RE_EMAIL.sub(" [email] ", text)

    # 2. Lowercase + risadas padronizadas
    text = text.lower()
    text = RE_LAUGHTER.sub(" kkk ", text)

    # 3. Redução de alongamentos emocionais
    text = reduce_lengthened_words(text)

    # 4. Separar números e letras (10min -> 10 min)
    text = RE_NUM_LETTER.sub(r"\1 \2", text)

    # 5. Remoção de acentos
    text = remove_accents(text)

    # 6. Normalização monetária básica (estrutura futura)
    text = text.replace("r$", " reais ").replace("$", " dolares ")

    # 7. Limpeza de símbolos (mantém tokens especiais)
    text = RE_NON_ALPHANUMERIC.sub(" ", text)

    # 8. Tokenização + substituição
    tokens: List[str] = text.split()
    normalized_tokens: List[str] = []

    for token in tokens:
        if token in ("[url]", "[email]"):
            normalized_tokens.append(token)
        else:
            normalized_tokens.append(REPLACEMENTS.get(token, token))

    # 9. Finalização
    result = " ".join(normalized_tokens)
    return RE_EXTRA_SPACES.sub(" ", result).strip()
