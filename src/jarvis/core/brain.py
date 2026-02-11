import json
import logging
import asyncio
from typing import Dict, Any

from jarvis.config import Config
from jarvis.database.persistence import Persistence
from jarvis.core.personality import Personality
from jarvis.nlp.local_brain import LocalBrain as LocalBrainEngine
from jarvis.core.llm_fallback import LLMFallbackEngine

logger = logging.getLogger("core.brain")


class Brain:
    """
    Brain é o ÚLTIMO recurso.
    Nunca executa ação.
    Nunca decide fluxo crítico.

    ARQUITETURA:
    1. Local Mini-Brain (Retrieval-Based) - Prioridade Máxima (Rápido, Local, Free)
    2. Cloud LLM (Gemini) - Fallback Cognitivo (Se configurado)
    3. Fallback Determinístico (Hardcoded) - Segurança Final
    """

    def __init__(self):
        # Mini-Brain: Inteligência local baseada em similaridade (Rápida e leve)
        self.local_brain = LocalBrainEngine()

        # Local LLM (Ollama) - Fallback quando nuvem indisponível
        self.local_llm = LLMFallbackEngine()

        # Cloud LLM: Opcional, se a chave estiver configurada
        self.cloud_llm = None
        if Config.GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=Config.GEMINI_API_KEY)
                self.cloud_llm = genai.GenerativeModel(Config.GEMINI_MODEL)
                logger.info(f"🧠 Cloud Brain (Gemini) ativado: {Config.GEMINI_MODEL}")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao inicializar Gemini: {e}")

        logger.info("🧠 Brain inicializado.")

    async def process_intent(self, user_text: str) -> Dict[str, Any]:
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
        # 2. CLOUD LLM (INTELIGÊNCIA REAL)
        # ==================================================
        if self.cloud_llm:
            try:
                # Prompt simples para chat contextual
                response = await asyncio.to_thread(
                    self.cloud_llm.generate_content,
                    f"Você é Jarvis do Cerrado, um assistente útil e engraçado com sotaque goiano leve. Responda curto: {user_text}"
                )

                if response and response.text:
                    return {
                        "intent": "chat",
                        "response": response.text.strip(),
                        "text": user_text,
                        "source": "cloud_llm",
                        "confidence": 0.9
                    }
            except Exception as e:
                logger.error(f"❌ Erro no Cloud Brain: {e}")
                # Se for erro de permissão (403), desativa permanentemente
                if "403" in str(e) or "API key" in str(e):
                    logger.warning("🚫 Cloud LLM desativado devido a erro de API Key.")
                    self.cloud_llm = None

        # ==================================================
        # 2.5 LOCAL LLM (OLLAMA FALLBACK)
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
        # 3. FALLBACK FINAL
        # ==================================================
        logger.info("[ROUTER] Fallback humano acionado (sem LLM).")
        return self._fallback(user_text)

    def _fallback(self, user_text: str) -> Dict[str, Any]:
        """
        Resposta padrão quando TUDO falha.
        """
        return {
            "intent": "chat",
            "response": Personality.get_response("FALLBACK"),
            "text": user_text,
            "confidence": 1.0,
        }
