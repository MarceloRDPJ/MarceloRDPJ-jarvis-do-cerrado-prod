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
                "Antes de salvar, qual é sua **meta diária** de água (em ml)?"
            )

        # Fluxo padrão (genérico)
        flow_state["step"] = "confirmation"
        ContextEngine.save_context(chat_id, {"flow": flow_state})

        minutes = params.get("minutes", 0)
        recurrence = "recorrente" if params.get("repeat") else "único"

        return (
            f"📝 Entendi: Lembrete *{recurrence}* a cada {minutes} minutos.\n"
            f"Texto: *{params.get('text')}*\n\n"
            "Confirma? (Sim/Não)"
        )

    @staticmethod
    def handle_response(chat_id: int, text: str, context_data: Dict) -> str:
        """
        Processa a resposta do usuário dentro do fluxo.
        """
        flow = context_data.get("flow")
        if not flow or flow["type"] != "reminder_creation":
            return None

        step = flow["step"]
        data = flow["data"]

        # --- Passo: Meta de Água ---
        if step == "ask_meta":
            # Tenta extrair número
            try:
                import re
                nums = re.findall(r'\d+', text)
                meta = int(nums[0]) if nums else 2000
                data["meta_ml"] = meta

                # Próximo passo: Copo
                flow["step"] = "ask_cup"
                flow["data"] = data
                ContextEngine.save_context(chat_id, {"flow": flow})
                return f"Ok, meta de {meta}ml. E qual o tamanho do seu **copo** (em ml)?"
            except:
                return "Não entendi o número. Digite apenas o valor (ex: 2000)."

        # --- Passo: Tamanho do Copo ---
        if step == "ask_cup":
            try:
                import re
                nums = re.findall(r'\d+', text)
                cup = int(nums[0]) if nums else 250
                data["cup_ml"] = cup

                # Finalizar
                return RemindersFlow.finalize_creation(chat_id, data)
            except:
                return "Não entendi o tamanho do copo. Ex: 250."

        # --- Passo: Confirmação Genérica ---
        if step == "confirmation":
            if text.lower() in ["sim", "s", "ok", "pode", "confirmo"]:
                return RemindersFlow.finalize_creation(chat_id, data)
            else:
                # Cancelar
                ContextEngine.clear_context(chat_id) # Limpa fluxo
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
        # ContextEngine.clear_context(chat_id) # Precisaria implementar clear parcial ou total
        # Por hora, sobrescrevemos com vazio ou deixamos expirar
        ContextEngine.save_context(chat_id, {})

        if action_type == "hydration":
            return (
                f"✅ **Lembrete de Hidratação Salvo!**\n"
                f"🎯 Meta: {meta['meta_ml']}ml | 🥛 Copo: {meta['cup_ml']}ml\n"
                f"⏰ A cada {minutes} minutos."
            )
        else:
            return f"✅ Lembrete salvo: *{text}* para daqui a {minutes} min."
