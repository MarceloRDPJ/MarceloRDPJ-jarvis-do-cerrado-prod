import logging
from typing import Dict, Any, List

from database.persistence import Persistence

logger = logging.getLogger("services.automations")


class AutomationsService:
    """
    AutomationsService — PASSO 9

    RESPONSABILIDADES:
    - Receber alertas do Guardian
    - Aplicar regras SE → ENTÃO
    - Gerar sugestões de ação
    - Registrar ações pendentes
    - NUNCA executar ações
    """

    @staticmethod
    def evaluate(diff: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Avalia mudanças e retorna sugestões de ação.
        """
        suggestions = []

        # =========================
        # NOVO DISPOSITIVO NA REDE
        # =========================
        if "network.device_count" in diff:
            before = diff["network.device_count"]["before"]
            after = diff["network.device_count"]["after"]

            if after > before:
                suggestions.append({
                    "type": "network.new_device",
                    "message": "Novo dispositivo detectado na rede.",
                    "suggestion": "Deseja bloquear o novo dispositivo?",
                    "action": {
                        "intent": "network_block_device",
                        "params": {}
                    }
                })

        # =========================
        # CPU ALTA
        # =========================
        cpu_key = "system.cpu_percent"
        if cpu_key in diff:
            cpu_now = diff[cpu_key]["after"]
            if cpu_now > 80:
                suggestions.append({
                    "type": "system.cpu_high",
                    "message": f"CPU alta detectada ({cpu_now}%).",
                    "suggestion": "Deseja reiniciar algum serviço ou o sistema?",
                    "action": {
                        "intent": "system_reboot",
                        "params": {}
                    }
                })

        return suggestions

    @staticmethod
    def register_pending(chat_id: int, suggestion: Dict[str, Any]):
        """
        Registra ação pendente aguardando autorização do usuário.
        """
        Persistence.set_state(
            f"pending_action:{chat_id}",
            suggestion
        )
