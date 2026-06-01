import logging
from typing import Dict, Any

from jarvis.config import Config
from jarvis.database.persistence import Persistence
from jarvis.core.personality import Personality
from jarvis.nlp.local_brain import LocalBrain as LocalBrainEngine
from jarvis.core.llm_fallback import LLMFallbackEngine
from jarvis.nlp.normalizer import normalize_text

logger = logging.getLogger("core.brain")


class Brain:
    """
    Brain é o ÚLTIMO recurso.
    Nunca executa ação.
    Nunca decide fluxo crítico.

    ARQUITETURA:
    1. Local Mini-Brain (Retrieval-Based) - Prioridade Máxima (Rápido, Local, Free)
    2. llama.cpp (Local LLM) - Fallback cognitivo 100% gratuito/local
    3. Fallback Determinístico (Hardcoded) - Segurança Final
    """

    def __init__(self):
        self.local_brain = LocalBrainEngine()
        self.local_llm = LLMFallbackEngine()
        logger.info("Brain inicializado (100% local/free).")

    async def process_intent(self, user_text: str, chat_id: int = None) -> Dict[str, Any]:
        """
        Chamado quando Rules e IntentEngine falham.
        Tenta LocalBrain primeiro, depois LLM local opcional.
        """

        # ==================================================
        # 0. GATE DE SETUP (CRÍTICO)
        # ==================================================
        lock_state = Persistence.get_state("lock")
        if lock_state and lock_state.get("setup_step"):
            logger.info("Brain ignorado (setup de fechadura ativo).")
            return {
                "intent": "lock_setup",
                "action": None,
                "entity": "lock",
                "text": user_text,
                "confidence": 1.0,
            }

        user_text = normalize_text(user_text)

        # ==================================================
        # 1. LOCAL MINI-BRAIN (RÁPIDO & FREE)
        # ==================================================
        try:
            local_result = await self.local_brain.process(user_text)
            if local_result:
                # Normaliza para estrutura de intent
                return {
                    "intent": "chat",
                    "response": local_result["text"], # O Executor espera 'response' para chat
                    "text": user_text,
                    "source": "local_brain",
                    "confidence": local_result["confidence"]
                }
        except Exception as e:
            logger.warning(f"⚠️ Erro no LocalBrain: {e}")

        # ==================================================
        # 2. LOCAL LLM (LLAMA.CPP / OFFLINE)
        # ==================================================
        try:
            local_response = self.local_llm.generate_chat_response(user_text)
            if local_response:
                return {
                    "intent": "chat",
                    "response": local_response,
                    "text": user_text,
                    "source": "local_llm",
                    "confidence": 0.8
                }
        except Exception as e:
            logger.warning(f"⚠️ Erro no Local LLM: {e}")

        # ==================================================
        # 3. FALLBACK FINAL
        # ==================================================
        logger.info("[ROUTER] Fallback humano acionado (sem LLM).")
        return self._fallback(user_text)

    def _fallback(self, user_text: str) -> Dict[str, Any]:
        """
        Resposta padrão quando TUDO falha.
        """
        try:
            Persistence.log_unknown_query(user_text, "final_fallback")
        except Exception:
            pass
        return {
            "intent": "chat",
            "response": Personality.get_response("FALLBACK"),
            "text": user_text,
            "confidence": 1.0,
        }
