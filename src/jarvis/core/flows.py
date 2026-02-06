import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from jarvis.database.persistence import Persistence
from jarvis.core.context import ContextEngine

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
            return (
                "💧 Certo. Vou te lembrar de beber água.\n"
                "Antes de salvar, qual é sua meta diária de água (em ml)?"
            )

        # Fluxo padrão (genérico)
        flow_state["step"] = "confirmation"
        ContextEngine.save_context(chat_id, {"flow": flow_state})

        minutes = params.get("minutes", 0)
        recurrence = "recorrente" if params.get("repeat") else "único"

        return (
            f"📝 Entendi: Lembrete {recurrence} a cada {minutes} minutos.\n"
            f"Texto: {params.get('text')}\n\n"
            "Confirma? (Sim/Não)"
        )

    @staticmethod
    def handle_response(chat_id: int, text: str, context_data: Dict) -> str:
        """
        Processa a resposta do usuário dentro do fluxo.
        """
        if not text:
             return "Não entendi."

        # Global Cancel / Back / Restart
        if text.lower().strip() in ["cancelar", "voltar", "reiniciar"]:
            # Clear flow only
            context_data.pop("flow", None)
            ContextEngine.save_context(chat_id, {"flow": None})
            return "🛑 Fluxo cancelado. Pode falar outra coisa."

        flow = context_data.get("flow")
        if not flow or flow["type"] != "reminder_creation":
            return None

        step = flow["step"]
        data = flow["data"]

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
                return f"Beleza. Meta diária: {num} ml.\nQual o volume do copo (em ml)?"
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
            if text.lower() in ["sim", "s", "ok", "pode", "confirmo", "beleza"]:
                return RemindersFlow.finalize_creation(chat_id, data)
            else:
                # Cancelar
                ContextEngine.save_context(chat_id, {"flow": None})
                return "❌ Lembrete cancelado."

        return "Não entendi. Responda a pergunta ou diga 'cancelar'."

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
            return (
                f"✅ Lembrete de Hidratação Salvo!\n"
                f"🎯 Meta: {meta['meta_ml']}ml | 🥛 Copo: {meta['cup_ml']}ml\n"
                f"⏰ A cada {minutes} minutos."
            )
        else:
            return f"✅ Lembrete salvo: {text} para daqui a {minutes} min."
