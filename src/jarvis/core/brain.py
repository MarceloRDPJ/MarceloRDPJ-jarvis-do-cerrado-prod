import json
import logging
from datetime import datetime

try:
    import google.generativeai as genai
except Exception:
    genai = None

from jarvis.config import Config
from jarvis.database.persistence import Persistence

logger = logging.getLogger("core.brain")


class Brain:
    """
    Brain é o ÚLTIMO recurso.
    Nunca executa ação.
    Nunca decide fluxo crítico.
    """

    def __init__(self):
        self.enabled = False

        if genai and Config.GEMINI_API_KEY:
            try:
                genai.configure(api_key=Config.GEMINI_API_KEY)
                self.model = genai.GenerativeModel(
                    model_name=Config.GEMINI_MODEL,
                    generation_config={"response_mime_type": "application/json"},
                )
                self.enabled = True
                logger.info("Brain (IA) inicializado.")
            except Exception as e:
                logger.warning(f"IA desativada: {e}")
                self.model = None
        else:
            self.model = None
            logger.warning("IA não configurada. Operando sem IA.")

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
        # IA DESATIVADA
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
            response = self.model.generate_content(prompt)
            raw = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)

            data.setdefault("intent", "unknown")
            data.setdefault("action", None)
            data.setdefault("entity", None)
            data.setdefault("confidence", 0.0)
            data["text"] = user_text

            return data

        except Exception as e:
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
