import json
import logging
from typing import Dict, Any

from jarvis.config import Config
from jarvis.database.persistence import Persistence
from jarvis.core.personality import Personality
from jarvis.nlp.local_brain import LocalBrain as LocalBrainEngine
from jarvis.core.llm_fallback import LLMFallbackEngine
from jarvis.core.context import ContextEngine
from datetime import timedelta
from jarvis.modules.system import SystemModule
from jarvis.modules.network import NetworkModule
from jarvis.nlp.normalizer import normalize_text

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
        self.cloud_client = None
        if Config.GEMINI_API_KEY:
            try:
                from google import genai
                self.cloud_client = genai.Client(api_key=Config.GEMINI_API_KEY)
                logger.info(f"🧠 Cloud Brain (Gemini) ativado: {Config.GEMINI_MODEL}")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao inicializar Gemini: {e}")

        logger.info("🧠 Brain inicializado.")

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
        # 2. CLOUD LLM (INTELIGÊNCIA REAL)
        # ==================================================
        if self.cloud_client:
            try:
                # Build system context
                system_context = ""
                try:
                    raw = await SystemModule.get_raw_status()
                    temp_str = f"{raw['temperature_c']}°C" if raw.get('temperature_c') else "N/A"
                    uptime_str = str(timedelta(seconds=raw['uptime_seconds']))
                    system_context = (
                        f"[SISTEMA]\n"
                        f"CPU: {raw['cpu_percent']}% | RAM: {raw['memory']['percent']}% | "
                        f"Temp: {temp_str} | Uptime: {uptime_str}\n"
                    )
                except: pass

                # Add network context
                try:
                    ping = await NetworkModule.get_ping_metrics()
                    internet_status = "Online" if ping.get('success') else "Offline"
                    latency = ping.get('latency_ms', 'N/A')
                    system_context += f"Internet: {internet_status} (latência: {latency}ms)\n"
                except: pass

                # Add conversation history if chat_id provided
                history_context = ""
                if chat_id:
                    ctx = ContextEngine.get_context(chat_id)
                    last_intent = ctx.get("last_intent", "unknown")
                    if last_intent:
                        history_context = f"[ÚLTIMA AÇÃO] Intenção: {last_intent}\n"

                prompt = (
                    f"Você é Jarvis do Cerrado, um assistente de automação residencial direto, técnico e com humor sutil (sotaque goiano leve). "
                    f"Responda de forma CURTA (1-3 frases), útil e precisa.\n\n"
                    f"{system_context}"
                    f"{history_context}"
                    f"[USUÁRIO] {user_text}\n"
                    f"[JARVIS]"
                )

                response = self.cloud_client.models.generate_content(
                    model=Config.GEMINI_MODEL,
                    contents=prompt
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
                    self.cloud_client = None

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
