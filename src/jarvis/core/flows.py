import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import re

from jarvis.database.persistence import Persistence
from jarvis.core.context import ContextEngine
from jarvis.core.personality import Personality
from jarvis.nlp.time_parser import parse_time_command, format_pt_br

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
        # Serialização de datetime para JSON (state)
        if params.get("target_date") and isinstance(params["target_date"], datetime):
            params["target_date"] = params["target_date"].isoformat()

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

        # Validação de Tempo
        target_date_iso = params.get("target_date")
        minutes = params.get("minutes", 0)

        if not target_date_iso and minutes <= 0:
            flow_state["step"] = "awaiting_clarification"
            flow_state["missing_field"] = "time"
            ContextEngine.save_context(chat_id, {"flow": flow_state})
            return "Certo. Que horas (e dia) você quer esse lembrete?"

        # Validação de Texto
        text = params.get("text")
        if not text or text.lower() == "lembrete":
            flow_state["step"] = "awaiting_clarification"
            flow_state["missing_field"] = "text"
            ContextEngine.save_context(chat_id, {"flow": flow_state})
            return "Sobre o que é o lembrete?"

        # Tudo certo -> Confirmação
        flow_state["step"] = "confirmation"
        ContextEngine.save_context(chat_id, {"flow": flow_state})

        # Formatação
        if target_date_iso:
            dt = datetime.fromisoformat(target_date_iso)
            time_display = format_pt_br(dt)
        else:
            # Fallback (não deve acontecer com novo parser, mas por segurança)
            dt = datetime.now() + timedelta(minutes=minutes)
            time_display = format_pt_br(dt)
            # Atualiza state com target_date calculado
            flow_state["data"]["target_date"] = dt.isoformat()
            ContextEngine.save_context(chat_id, {"flow": flow_state})

        return (
            f"Então ficou assim:\n"
            f"📅 {time_display}\n"
            f"📝 {text}\n"
            f"Confirma?"
        )

    @staticmethod
    def handle_response(chat_id: int, text: str, context_data: Dict) -> str:
        """
        Processa a resposta do usuário dentro do fluxo.
        """
        if not text:
             return "Não entendi."

        # Cancelamento Global dentro do fluxo
        stop_words = ["cancelar", "voltar", "reiniciar", "não", "nao", "cancel", "esquece", "deixa"]

        # Se for apenas "não" na confirmação, tratamos como cancelamento também.
        # Mas vamos verificar o step.

        flow = context_data.get("flow")
        if not flow or flow["type"] != "reminder_creation":
            return None

        step = flow["step"]
        data = flow["data"]

        # Cancelamento Explicito
        if text.lower().strip() in stop_words:
            context_data.pop("flow", None)
            ContextEngine.save_context(chat_id, {"flow": None})
            return "Beleza, cancelei o lembrete. Contexto limpo."

        # --- Passo: Clarificação (Tempo) ---
        if step == "awaiting_clarification" and flow.get("missing_field") == "time":
            time_data = parse_time_command(text)

            if time_data["target_date"]:
                data["target_date"] = time_data["target_date"].isoformat()
                data["minutes"] = time_data["minutes"]
                data["repeat"] = time_data["is_recurring"] or data.get("repeat", False)
                data["recurrence"] = time_data["recurrence"]

                # Se ainda faltar texto
                if not data.get("text") or data.get("text").lower() == "lembrete":
                    flow["step"] = "awaiting_clarification"
                    flow["missing_field"] = "text"
                    flow["data"] = data
                    ContextEngine.save_context(chat_id, {"flow": flow})
                    return "E qual é o assunto do lembrete?"

                # Avança para confirmação
                flow["step"] = "confirmation"
                flow["data"] = data
                flow.pop("missing_field", None)

                ContextEngine.save_context(chat_id, {"flow": flow})

                dt = time_data["target_date"]
                time_display = format_pt_br(dt)

                return (
                    f"Então ficou assim:\n"
                    f"📅 {time_display}\n"
                    f"📝 {data.get('text')}\n"
                    f"Confirma?"
                )
            else:
                return "Ainda não entendi o horário. Tenta dizer algo como 'sábado às 14h' ou 'daqui 10 minutos'."

        # --- Passo: Clarificação (Texto) ---
        if step == "awaiting_clarification" and flow.get("missing_field") == "text":
            data["text"] = text

            # Avança para confirmação
            flow["step"] = "confirmation"
            flow["data"] = data
            flow.pop("missing_field", None)
            ContextEngine.save_context(chat_id, {"flow": flow})

            # Recupera data
            if data.get("target_date"):
                dt = datetime.fromisoformat(data["target_date"])
                time_display = format_pt_br(dt)
            else:
                time_display = "horário indefinido (erro)"

            return (
                f"Então ficou assim:\n"
                f"📅 {time_display}\n"
                f"📝 {text}\n"
                f"Confirma?"
            )

        # --- Passo: Meta de Água ---
        if step == "ask_meta":
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
            if text.lower() in ["sim", "s", "ok", "pode", "confirmo", "beleza", "bora", "pode ser", "isso"]:
                return RemindersFlow.finalize_creation(chat_id, data)
            else:
                # Cancelar (Se falou qualquer outra coisa que não seja sim)
                ContextEngine.save_context(chat_id, {"flow": None})
                return "Entendido. Lembrete cancelado."

        return "Não entendi o que você disse. O fluxo está confuso."

    @staticmethod
    def finalize_creation(chat_id: int, data: Dict) -> str:
        """
        Salva no banco e retorna mensagem final.
        """
        text = data.get("text")
        minutes = data.get("minutes", 0)
        repeat = data.get("repeat")
        action_type = data.get("action_type", "default")
        target_date_iso = data.get("target_date")

        # Meta dados
        meta = {}
        if action_type == "hydration":
            meta["meta_ml"] = data.get("meta_ml", 2000)
            meta["cup_ml"] = data.get("cup_ml", 250)

        # Calcular next_run
        if target_date_iso:
             next_run = datetime.fromisoformat(target_date_iso)
             # Recalcula minutes para o scheduler (delta)
             now = datetime.now() # Naive/Local to match logic in parser
             # Wait, persistence uses UTC.
             # We should probably trust next_run as absolute.
             # But Persistence.add_task expects next_run.
             # We need to make sure next_run is offset-aware or consistent.
             # Current project seems to mix naive and UTC.
             # Let's try to stick to what parser returns (naive local) and let persistence handle it or convert.
             # Persistence.add_task takes datetime and calls .isoformat().

        else:
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

        # Formatação Final
        time_display = format_pt_br(next_run)

        if action_type == "hydration":
            return f"Hidratação configurada! Meta: {meta['meta_ml']}ml."
        else:
            return f"Combinado. Lembrete salvo para {time_display}."

    @staticmethod
    def list_reminders(chat_id: int) -> str:
        """
        Lista lembretes ativos formatados humanamente.
        """
        tasks = Persistence.get_active_tasks(chat_id)

        if not tasks:
            return "Você não tem nenhum lembrete ativo no momento."

        response = "📅 Seus Lembretes:\n"

        for i, task in enumerate(tasks, 1):
            next_run_iso = task['next_run']
            try:
                dt = datetime.fromisoformat(next_run_iso)
                time_display = format_pt_br(dt)
            except ValueError:
                time_display = "Data inválida"

            text = task['text']
            # Se for recorrente, indica
            if task['type'] == 'recurring':
                time_display += " (Recorrente)"

            response += f"{i}️⃣ {time_display} — {text}\n"

        return response

    @staticmethod
    def delete_reminder(chat_id: int, index: int) -> str:
        """
        Apaga um lembrete pelo índice da lista.
        """
        tasks = Persistence.get_active_tasks(chat_id)

        if index < 1 or index > len(tasks):
            return f"Não encontrei o lembrete número {index}. Tente 'listar lembretes' para ver os números."

        task_to_delete = tasks[index - 1]
        Persistence.update_task_status(task_to_delete['id'], 'cancelled')

        return f"Feito. Lembrete '{task_to_delete['text']}' apagado."
