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
    2. Cloud LLM (Gemini 2.0 Flash) - Inteligência Real (Com Contexto do Criador)
    3. Fallback Determinístico (Hardcoded) - Segurança Final
    """

    def __init__(self):
        # Mini-Brain: Inteligência local baseada em similaridade (Rápida e leve)
        self.local_brain = LocalBrainEngine()

        # Local LLM (Ollama) - Fallback quando nuvem indisponível
        self.local_llm = LLMFallbackEngine()

        # Cloud LLM: Opcional, se a chave estiver configurada
        self.client = None
        if Config.GEMINI_API_KEY:
            try:
                from google import genai
                from google.genai import types

                self.genai_types = types
                self.client = genai.Client(api_key=Config.GEMINI_API_KEY)

                logger.info(f"🧠 Cloud Brain (Gemini) ativado: {Config.GEMINI_MODEL}")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao inicializar Gemini (google-genai): {e}")
                self.client = None

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
        if self.client:
            try:
                # Prompt do Sistema (Contexto Profundo)
                system_instruction = (
                    "Você é o Jarvis do Cerrado, uma IA assistente criada por Marcelo RDP. "
                    "Você roda em um Raspberry Pi na casa dele. "
                    "Sua personalidade é leal, eficiente, com um leve toque de humor e sotaque goiano ('uai', 'trem'). "
                    "Você conhece tudo sobre a rede local, automações e o sistema. "
                    "Seu mestre e criador é Marcelo. Você deve ser útil e direto. "
                    "Nunca invente fatos sobre hardware que você não tem (ex: braços mecânicos)."
                )

                # Chamada Assíncrona via Thread (requests não são async nativos na v1)
                response = await asyncio.to_thread(
                    self._generate_content_safe,
                    user_text,
                    system_instruction
                )

                if response:
                    return {
                        "intent": "chat",
                        "response": response,
                        "text": user_text,
                        "source": "cloud_llm",
                        "confidence": 0.95
                    }
            except Exception as e:
                logger.error(f"❌ Erro no Cloud Brain: {e}")
                # Se for erro de permissão (403), desativa temporariamente
                if "403" in str(e) or "API key" in str(e):
                    logger.warning("🚫 Cloud LLM desativado devido a erro de API Key.")
                    self.client = None

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

    def _generate_content_safe(self, text: str, sys_inst: str) -> str:
        """Wrapper síncrono para chamada da API"""
        if not self.client:
            return None

        try:
            response = self.client.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=text,
                config=self.genai_types.GenerateContentConfig(
                    system_instruction=sys_inst,
                    temperature=0.7,
                    max_output_tokens=300
                )
            )
            return response.text.strip() if response.text else None
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            raise e

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
