import json
import logging
import asyncio
from datetime import datetime

from jarvis.config import Config
from jarvis.database.persistence import Persistence
from jarvis.core.llm_fallback import LLMFallbackEngine
from jarvis.core.personality import Personality

logger = logging.getLogger("core.brain")


class Brain:
    """
    Brain é o ÚLTIMO recurso.
    Nunca executa ação.
    Nunca decide fluxo crítico.

    ARQUITETURA:
    1. Local LLM (Ollama/TinyLlama) - Prioridade
    2. Fallback Determinístico (Hardcoded) - Segurança

    🚫 Google AI REMOVIDO (Fase 3 compliancy)
    """

    def __init__(self):
        self.local_llm = LLMFallbackEngine()
        logger.info("Brain (Local Only) inicializado.")

    async def process_intent(self, user_text: str) -> dict:
        """
        Só é chamado se rules NÃO reconhecerem o comando.
        """

        # ==================================================
        # 🚫 GATE CRÍTICO: NÃO USAR IA DURANTE SETUP
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

        # ==================================================
        # 1. LOCAL LLM (PHASE 3)
        # ==================================================
        try:
            local_result = await asyncio.to_thread(self.local_llm.interpret, user_text)
            if local_result:
                local_result.setdefault("intent", "unknown")
                local_result.setdefault("action", None)
                local_result.setdefault("entity", None)
                local_result.setdefault("confidence", 0.8) # Arbitrary low confidence for LLM
                local_result["text"] = user_text
                local_result["source"] = "local_llm"

                logger.info(f"[LLM] Local fallback interpretou: {local_result.get('intent')}")
                return local_result
        except Exception as e:
            logger.warning(f"[LLM] Erro ao processar localmente: {e}")

        # ==================================================
        # 2. FALLBACK DETERMINÍSTICO (SEGURANÇA FINAL)
        # ==================================================
        logger.info("[ROUTER] Fallback humano acionado (sem LLM).")
        return self._fallback(user_text)

    def _fallback(self, user_text: str) -> dict:
        """
        Resposta padrão quando TUDO falha.
        Deve ser útil e guiar o usuário de volta aos trilhos.
        """
        return {
            "intent": "chat",
            "response": Personality.get_response("FALLBACK"),
            "text": user_text,
            "confidence": 1.0,
        }
