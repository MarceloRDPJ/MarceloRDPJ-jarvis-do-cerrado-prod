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
    2. Crof AI (OpenAI-compatible) - Fallback Cognitivo Econômico (tools para ações)
    3. Ollama (Local LLM) - Fallback offline
    4. Fallback Determinístico (Hardcoded) - Segurança Final
    """

    def __init__(self):
        self.local_brain = LocalBrainEngine()
        self.local_llm = LLMFallbackEngine()

        self.crof = None
        if Config.CROF_API_KEY:
            try:
                from jarvis.core.crof_ai import CrofAIEngine
                self.crof = CrofAIEngine(api_key=Config.CROF_API_KEY, model=Config.CROF_MODEL)
                logger.info(f"Crof AI ativado (modelo: {Config.CROF_MODEL})")
            except Exception as e:
                logger.warning(f"Erro ao inicializar Crof AI: {e}")

        logger.info("Brain inicializado.")

    async def process_intent(self, user_text: str, chat_id: int = None) -> Dict[str, Any]:
        """
        Chamado quando Rules e IntentEngine falham.
        Tenta LocalBrain primeiro, depois Cloud LLM.
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
        # 2. CROF AI (ECONÔMICO, TOOLS, AUTÔNOMO)
        # ==================================================
        if self.crof:
            try:
                crof_result = await self.crof.process(user_text, chat_id=chat_id)
                if crof_result:
                    return crof_result
            except Exception as e:
                logger.warning(f"Crof AI error: {e}")

        # ==================================================
        # 3. LOCAL LLM (OLLAMA OFFLINE FALLBACK)
        # ==================================================
        # Se chegou aqui, Cloud falhou ou não existe.
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
        # 4. FALLBACK FINAL
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
