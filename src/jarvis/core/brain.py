import json
import logging
import asyncio
from datetime import datetime

try:
    from google import genai
except Exception:
    genai = None

from jarvis.config import Config
from jarvis.database.persistence import Persistence
from jarvis.core.llm_fallback import LLMFallbackEngine

logger = logging.getLogger("core.brain")


class Brain:
    """
    Brain é o ÚLTIMO recurso.
    Nunca executa ação.
    Nunca decide fluxo crítico.
    """

    def __init__(self):
        self.enabled = False
        self.local_llm = LLMFallbackEngine()

        if genai and Config.GEMINI_API_KEY:
            try:
                self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
                self.enabled = True
                logger.info("Brain (Gemini) inicializado.")
            except Exception as e:
                logger.warning(f"IA (Gemini) desativada: {e}")
                self.client = None
        else:
            self.client = None
            logger.warning("Gemini não configurado.")

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
        local_result = await asyncio.to_thread(self.local_llm.interpret, user_text)
        if local_result:
            local_result.setdefault("intent", "unknown")
            local_result.setdefault("action", None)
            local_result.setdefault("entity", None)
            local_result.setdefault("confidence", 0.8) # Arbitrary low confidence for LLM
            local_result["text"] = user_text
            local_result["source"] = "local_llm"
            return local_result

        # ==================================================
        # 2. CLOUD LLM (GEMINI)
        # ==================================================
        if not self.enabled:
            return self._fallback(user_text)

        prompt = f"""
Data: {datetime.now().isoformat()}

Interprete a frase abaixo e responda SOMENTE JSON:

Formato:
{{
  "intent": "chat|unknown",
  "action": null,
  "entity": null,
  "confidence": 0.0
}}

Frase:
"{user_text}"
"""

        try:
            response = self.client.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            raw = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)

            data.setdefault("intent", "unknown")
            data.setdefault("action", None)
            data.setdefault("entity", None)
            data.setdefault("confidence", 0.0)
            data["text"] = user_text

            return data

        except Exception as e:
            if "403" in str(e) or "PERMISSION_DENIED" in str(e):
                logger.critical("🚨 API KEY BLOQUEADA/REVOGADA! Verifique o Google AI Studio.")
                return {
                     "intent": "chat",
                     "response": "⚠️ Minha chave de cérebro (API Key) foi revogada. Preciso de uma nova lá no .env!",
                     "confidence": 1.0
                }

            logger.warning(f"IA falhou (ignorado): {e}")
            return self._fallback(user_text)

    def _fallback(self, user_text: str) -> dict:
        return {
            "intent": "chat",
            "action": None,
            "entity": None,
            "text": user_text,
            "confidence": 0.0,
        }
