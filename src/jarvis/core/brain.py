import logging
import json
from typing import Dict, Any, Optional

from jarvis.config import Config
from jarvis.database.persistence import Persistence
from jarvis.core.personality import Personality
from jarvis.nlp.local_brain import LocalBrain as LocalBrainEngine
from jarvis.core.llm_fallback import LLMFallbackEngine
from jarvis.nlp.normalizer import normalize_text

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


class Brain:
    """
    Cérebro central do Jarvis.
    Participa ativamente da interpretação e decisão de roteamento.
    """

    def __init__(self):
        self.local_brain = LocalBrainEngine()
        self.local_llm = LLMFallbackEngine()
        logger.info("Brain inicializado (100% local/free).")

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

        # Se LLM estiver offline, retorna None (router decide)
        if not self.local_llm.is_available():
            return None

        # Prompt curto pro LLM classificar
        prompt = (
            "Classifique o texto em: COMANDO ou CONVERSA.\n"
            "COMANDO = pedido pra executar ação no sistema (rede, lembrete, sistema, hidratação, fan, ajuda).\n"
            "CONVERSA = pergunta geral, papo, opinião, curiosidade, explicação.\n"
            f"Texto: {user_text}\n"
            "Responda apenas: COMANDO ou CONVERSA"
        )

        try:
            resposta = self.local_llm.generate_chat_response(prompt)
            if not resposta:
                return None

            classificacao = resposta.strip().upper()

            if "COMANDO" in classificacao:
                return {"type": "command", "confidence": 0.9, "source": "brain_llm"}
            elif "CONVERSA" in classificacao:
                return {"type": "chat", "confidence": 0.9, "source": "brain_llm"}
            else:
                return None
        except Exception as e:
            logger.warning(f"Erro no Brain.classify: {e}")
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
                    "response": local_result["text"],
                    "text": user_text,
                    "source": "local_brain",
                    "confidence": local_result["confidence"]
                }
        except Exception as e:
            logger.warning(f"Erro no LocalBrain: {e}")

        # ==================================================
        # 2. LLM LOCAL (CÉREBRO PRINCIPAL)
        # ==================================================
        try:
            local_response = self.local_llm.generate_chat_response(user_text)
            if local_response:
                return {
                    "intent": "chat",
                    "response": local_response,
                    "text": user_text,
                    "source": "local_llm",
                    "confidence": 0.85
                }
        except Exception as e:
            logger.warning(f"Erro no Local LLM: {e}")

        # ==================================================
        # 3. FALLBACK FINAL
        # ==================================================
        logger.info("Fallback humano acionado (sem LLM).")
        return self._fallback(user_text)

    def _fallback(self, user_text: str) -> Dict[str, Any]:
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
