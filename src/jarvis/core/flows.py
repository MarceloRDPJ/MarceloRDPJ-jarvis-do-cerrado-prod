import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from jarvis.database.persistence import Persistence
from jarvis.core.context import ContextEngine
from jarvis.core.personality import Personality

logger = logging.getLogger("core.flows")

class RemindersFlow:
    """
    Gerencia o fluxo interativo de criação de lembretes.
    """

    @staticmethod
    def start_flow(chat_id: int, params: Dict[str, Any]) -> str:
        """
        Inicia o fluxo de confirmação.
        Salva o estado temporário e retorna a primeira pergunta.
        """

        # Salva o estado da intenção de criar lembrete
        # Usamos o ContextEngine ou um estado específico de fluxo
        # Aqui vamos simplificar usando o contexto de "pending_action" ou similar
        # Mas como é um fluxo de perguntas, precisamos de um estado de conversação.

        # Estrutura do estado do fluxo
        flow_state = {
            "type": "reminder_creation",
            "step": "confirm_details",
            "data": params,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Se for hidratação, perguntar meta
        if params.get("action_type") == "hydration":
            flow_state["step"] = "ask_meta"
            ContextEngine.save_context(chat_id, {"flow": flow_state})
            return Personality.FLOW_REMINDER_ASK_META

        # Fluxo padrão (genérico)
        minutes = params.get("minutes", 0)

        # 1. Validação de Tempo (Regra de Ouro)
        if minutes <= 0:
            flow_state["step"] = "awaiting_clarification"
            flow_state["missing_field"] = "time"
            ContextEngine.save_context(chat_id, {"flow": flow_state})
            return Personality.FLOW_REMINDER_ASK_TIME

        flow_state["step"] = "confirmation"
        ContextEngine.save_context(chat_id, {"flow": flow_state})

        recurrence = "recorrente" if params.get("repeat") else "único"

        return Personality.FLOW_REMINDER_CONFIRM.format(
            recurrence=recurrence,
            minutes=minutes,
            text=params.get('text')
        )

    @staticmethod
    def handle_response(chat_id: int, text: str, context_data: Dict) -> str:
        """
        Processa a resposta do usuário dentro do fluxo.
        """
        if not text:
             return Personality.get_response("ERROR")

        # Global Cancel / Back / Restart / Negative
        stop_words = ["cancelar", "voltar", "reiniciar", "não", "nao", "cancel"]
        if text.lower().strip() in stop_words:
            # Clear flow only
            context_data.pop("flow", None)
            ContextEngine.save_context(chat_id, {"flow": None})
            return Personality.FLOW_REMINDER_CANCEL

        flow = context_data.get("flow")
        if not flow or flow["type"] != "reminder_creation":
            return None

        step = flow["step"]
        data = flow["data"]

        # --- Passo: Clarificação (Tempo) ---
        if step == "awaiting_clarification" and flow.get("missing_field") == "time":
            from jarvis.nlp.time_parser import parse_time_command

            # Tenta parser novamente com a resposta do usuário
            # Ex: "meio dia", "10 minutos"
            time_data = parse_time_command(text)

            if time_data["minutes"] > 0:
                data["minutes"] = time_data["minutes"]
                data["repeat"] = time_data["is_recurring"] or data.get("repeat", False)
                data["recurrence"] = time_data["recurrence"]

                # Avança para confirmação
                flow["step"] = "confirmation"
                flow["data"] = data
                # Limpa campo faltante
                flow.pop("missing_field", None)

                ContextEngine.save_context(chat_id, {"flow": flow})

                recurrence = "recorrente" if data["repeat"] else "único"
                return Personality.FLOW_REMINDER_CONFIRM.format(
                    recurrence=recurrence,
                    minutes=data["minutes"],
                    text=data.get('text')
                )
            else:
                # Ainda não entendeu
                return "Ainda não entendi o horário. Tenta dizer algo como 'em 10 minutos' ou 'as 14h'."

        # --- Passo: Meta de Água ---
        if step == "ask_meta":
            import re
            # Normalização de número (ex: 6 litros -> 6000)
            match = re.search(r'(\d+)\s*(l|ml|litros?)?', text, re.IGNORECASE)

            if match:
                num = int(match.group(1))
                unit = match.group(2)

                if unit and unit.lower().startswith('l'):
                    num *= 1000

                data["meta_ml"] = num

                # Próximo passo: Copo
                flow["step"] = "ask_cup"
                flow["data"] = data
                ContextEngine.save_context(chat_id, {"flow": flow})
                return Personality.FLOW_REMINDER_ASK_CUP
            else:
                return "Não entendi o número. Tenta de novo (ex: 2000 ou 2 litros)."

        # --- Passo: Tamanho do Copo ---
        if step == "ask_cup":
            import re
            match = re.search(r'(\d+)\s*(ml)?', text, re.IGNORECASE)

            if match:
                cup = int(match.group(1))
                data["cup_ml"] = cup

                # Finalizar
                return RemindersFlow.finalize_creation(chat_id, data)
            else:
                return "Não entendi o tamanho do copo. Ex: 250."

        # --- Passo: Confirmação Genérica ---
        if step == "confirmation":
            if text.lower() in ["sim", "s", "ok", "pode", "confirmo", "beleza", "bora", "pode ser"]:
                return RemindersFlow.finalize_creation(chat_id, data)
            else:
                # Cancelar (fallback)
                ContextEngine.save_context(chat_id, {"flow": None})
                return Personality.FLOW_REMINDER_CANCEL

        return Personality.get_response("ERROR")

    @staticmethod
    def finalize_creation(chat_id: int, data: Dict) -> str:
        """
        Salva no banco e retorna mensagem final.
        """
        text = data.get("text")
        minutes = data.get("minutes")
        repeat = data.get("repeat")
        action_type = data.get("action_type", "default")

        # Meta dados
        meta = {}
        if action_type == "hydration":
            meta["meta_ml"] = data.get("meta_ml", 2000)
            meta["cup_ml"] = data.get("cup_ml", 250)

        # Calcular next_run
        now = datetime.now(timezone.utc)
        next_run = now + timedelta(minutes=minutes)

        task_type = "recurring" if repeat else "unique"

        Persistence.add_task(
            chat_id=chat_id,
            text=text,
            next_run=next_run,
            action=action_type,
            task_type=task_type,
            interval_minutes=minutes,
            meta=meta
        )

        # Limpa fluxo
        ContextEngine.save_context(chat_id, {"flow": None})

        if action_type == "hydration":
            return Personality.FLOW_REMINDER_SAVED_HYDRATION.format(
                meta=meta['meta_ml'],
                cup=meta['cup_ml'],
                minutes=minutes
            )
        else:
            return Personality.FLOW_REMINDER_SAVED.format(
                text=text,
                minutes=minutes
            )
