import logging
import json
from typing import Dict, Any, Optional

from jarvis.config import Config
from jarvis.database.persistence import Persistence
from jarvis.core.personality import Personality
from jarvis.nlp.local_brain import LocalBrain as LocalBrainEngine
from jarvis.core.llm_fallback import LLMFallbackEngine
from jarvis.nlp.normalizer import normalize_text
from jarvis.tools.current_info import CurrentInfo, CURRENT_MARKERS

logger = logging.getLogger("core.brain")

# Intenções de comando que o Brain reconhece
COMMAND_INTENTS = {
    "network_scan", "network_speed", "network_status", "network_stats",
    "network_block", "network_rename", "network_block_site",
    "system_status", "system_logs", "system_reboot", "system_restart_adguard",
    "fan_control",
    "reminder_set", "reminder_list", "reminder_today", "reminder_overdue",
    "reminder_delete", "reminder_update",
    "hydration_activate", "hydration_log", "hydration_status",
    "hydration_analytics", "hydration_control", "hydration_update",
    "wake_pc", "pc_status", "help", "menu_rede", "menu_agenda",
    "menu_automacoes", "menu_sistema", "automation_list", "automation_config",
    "token_usage", "daily_report", "unknown_queries",
}

CURRENT_QUESTION_MARKERS = CURRENT_MARKERS


class Brain:
    """
    Cérebro central do Jarvis.
    Participa ativamente da interpretação e decisão de roteamento.
    """

    def __init__(self):
        self.local_brain = LocalBrainEngine()
        self.local_llm = LLMFallbackEngine()
        self.current_info = CurrentInfo()
        logger.info("Brain inicializado (LocalBrain + LLM local + ferramentas web locais).")

    async def classify_intent(self, user_text: str) -> Optional[Dict[str, Any]]:
        """
        Classifica se o texto é um COMANDO ou CONVERSA.
        Usa o LLM local como cérebro para tomar a decisão.
        Retorna None se não conseguir classificar (offline/erro).
        """
        user_text = normalize_text(user_text)

        # LocalBrain: só aceita se for match quase exato (>= 95%)
        # Evita falsos positivos tipo "o que e dns" → "voce e homem ou mulher"
        try:
            local_result = await self.local_brain.process(user_text)
            if local_result and local_result.get("confidence", 0) >= 0.95:
                return {
                    "type": "chat",
                    "intent": "chat",
                    "response": local_result["text"],
                    "confidence": local_result["confidence"],
                    "source": "local_brain",
                }
        except Exception:
            pass

        # Classificação por LLM local foi removida do caminho principal.
        # O router decide por heurística leve e segura quando o LocalBrain não sabe.
        return None

    async def process_intent(self, user_text: str, chat_id: int = None) -> Dict[str, Any]:
        """
        Gera resposta de conversa (chat) usando o LLM como cérebro principal.
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
        # 1. LOCAL MINI-BRAIN (RÁPIDO - só com confiança alta)
        # ==================================================
        try:
            local_result = await self.local_brain.process(user_text)
            if local_result and local_result.get("confidence", 0) >= 0.90:
                return {
                    "intent": "chat",
                    "params": {"response": local_result["text"]},
                    "text": user_text,
                    "source": "local_brain",
                    "confidence": local_result["confidence"]
                }
        except Exception as e:
            logger.warning(f"Erro no LocalBrain: {e}")

        if self._asks_internet_status(user_text):
            return self._chat_response(self._internet_status_response(), user_text, "config_status", 1.0)

        is_current_question = self._is_current_question(user_text)
        if is_current_question:
            current_result = self.current_info.collect(user_text)
            if current_result.ok and current_result.answer:
                return self._chat_response(current_result.answer, user_text, current_result.source, 0.95)
            if current_result.ok and current_result.context:
                try:
                    local_response = self.local_llm.generate_response_with_context(user_text, current_result.context)
                    if local_response:
                        return self._chat_response(local_response, user_text, f"local_llm_{current_result.source}", 0.90)
                except Exception as e:
                    logger.warning(f"Erro no LLM local com contexto atual: {e}")
                return self._chat_response(
                    "Consegui coletar dados atuais, mas o LLM local não respondeu a tempo para formular a resposta.",
                    user_text,
                    "local_llm_context_failed",
                    0.70,
                )
            return self._chat_response(
                f"Não consegui consultar uma fonte local gratuita para isso agora. Motivo: {current_result.error}",
                user_text,
                current_result.source,
                0.80,
            )

        # ==================================================
        # 2. LLM LOCAL (PERGUNTAS ABERTAS)
        # ==================================================
        try:
            local_response = self.local_llm.generate_chat_response(user_text)
            if local_response:
                return self._chat_response(local_response, user_text, "local_llm", 0.85)
        except Exception as e:
            logger.warning(f"Erro no Local LLM: {e}")

        # ==================================================
        # 3. FALLBACK FINAL
        # ==================================================
        logger.info("Fallback amigável acionado (LLM/web indisponível).")
        return await self._fallback(user_text)

    def _is_current_question(self, user_text: str) -> bool:
        return any(marker in user_text for marker in CURRENT_QUESTION_MARKERS)

    def _asks_internet_status(self, user_text: str) -> bool:
        return "acesso a internet" in user_text or "acessa internet" in user_text

    def _internet_status_response(self) -> str:
        llm_status = "configurado" if self.local_llm.is_available() else "indisponível"
        return (
            f"Estou rodando em modo local. Meu LLM local está {llm_status} e eu não uso APIs pagas de LLM. "
            "Para dados atuais, tento ferramentas locais gratuitas de internet, RSS e fontes públicas leves."
        )

    def _chat_response(self, response: str, user_text: str, source: str, confidence: float) -> Dict[str, Any]:
        return {
            "intent": "chat",
            "params": {"response": response},
            "text": user_text,
            "source": source,
            "confidence": confidence,
        }

    async def _fallback(self, user_text: str) -> Dict[str, Any]:
        try:
            Persistence.log_unknown_query(user_text, "final_fallback")
        except Exception:
            pass

        # Fallback inteligente: tenta LocalBrain como última alternativa
        try:
            local_result = await self.local_brain.process(user_text)
            if local_result and local_result.get("confidence", 0) >= 0.80:
                return {
                    "intent": "chat",
                    "params": {"response": local_result["text"]},
                    "text": user_text,
                    "source": "local_brain_fallback",
                    "confidence": local_result["confidence"],
                }
        except Exception:
            pass

        return {
            "intent": "chat",
            "params": {"response": Personality.get_response("FALLBACK")},
            "text": user_text,
            "confidence": 1.0,
        }
