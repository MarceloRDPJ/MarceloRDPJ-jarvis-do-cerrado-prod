import logging
import json
import random
from typing import Dict, Any, List
from rapidfuzz import process, fuzz, utils

logger = logging.getLogger(__name__)

class LocalBrain:
    """
    Mini-Brain: Uma inteligência local leve baseada em similaridade (Retrieval-Based).
    Funciona como um fallback inteligente quando a IA Generativa falha ou está lenta.
    Ideal para Raspberry Pi.
    """

    def __init__(self):
        # Base de Conhecimento Local (Knowledge Base)
        self.kb = {
            "quem é você": "Sou o Jarvis do Cerrado, seu assistente pessoal com sotaque e tecnologia de ponta. Cuido da sua casa e da sua rede.",
            "quem e voce": "Sou o Jarvis do Cerrado, seu assistente pessoal com sotaque e tecnologia de ponta. Cuido da sua casa e da sua rede.",
            "qual seu nome": "Me chamo Jarvis. Mas pode me chamar de Guardião, se preferir.",
            "o que você faz": "Eu monitoro a rede, cuido dos seus lembretes, aviso se a internet cair e ainda bato um papo. Sou multitarefa, uai.",
            "piada": [
                "Por que o computador foi ao médico? Porque estava com vírus! kkk",
                "O que o servidor disse pro cliente? Nada, ele caiu.",
                "Sabe qual a tecla preferida do astronauta? A barra de espaço."
            ],
            "tudo bem": "Tudo tranquilo como água de poço. E com você?",
            "obrigado": ["Por nada!", "Tamo junto!", "Qualquer coisa, grita."],
            "status": "Tô rodando liso aqui no Raspberry Pi. Tudo sob controle.",
            "quem criou você": "Fui forjado nas linhas de código com muito café e pão de queijo.",
            "como você está": "Operacional e pronto pro serviço.",
            "boa noite": "Boa noite! Se for dormir, bom descanso. Eu fico de vigia.",
            "bom dia": "Bom dia! Bora fazer acontecer hoje?",
            "agradeço": "Eu que agradeço a preferência!",
            "valeu": "É nóis!",
            "tchau": "Até mais! Fico na escuta.",
            "jarvis": "Opa, tô na área.",
            "inteligencia": "Minha inteligência é híbrida: metade código, metade gambiarra chique (brincadeira, é tecnologia de ponta).",
            "cerveja": "Se eu pudesse, aceitava uma gelada. Mas cuidado com eletrônicos e líquidos!",
            "futebol": "Não torço pra time, torço pra internet não cair na hora do jogo.",
            "ping": "Pong! 🏓",
            "teste": "Testando 1, 2, 3... Câmbio.",
            "ola": "Opa, bão?",
        }

        # Flatten keys for fuzzy matching
        self.kb_keys = list(self.kb.keys())
        self.similarity_threshold = 75 # Lowered for better matching of typos/accents

    async def process(self, text: str) -> Dict[str, Any]:
        """
        Processa o texto tentando encontrar uma resposta na base local.
        """
        if not text:
            return None

        # Busca a melhor correspondência usando processador padrão (lowercase + strip)
        match_result = process.extractOne(
            text,
            self.kb_keys,
            scorer=fuzz.WRatio,
            processor=utils.default_process,
            score_cutoff=self.similarity_threshold
        )

        if match_result:
            matched_key, score, _ = match_result
            response = self.kb[matched_key]

            # Se for lista, escolhe um aleatório
            if isinstance(response, list):
                response = random.choice(response)

            logger.info(f"LocalBrain matched '{text}' -> '{matched_key}' (Score: {score})")

            return {
                "intent": "chat",
                "text": response,
                "source": "local_brain",
                "confidence": score / 100.0
            }

        return None
