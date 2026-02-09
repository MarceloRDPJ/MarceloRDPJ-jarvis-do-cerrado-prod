import logging
import random
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from jarvis.database.persistence import Persistence
from jarvis.core.context import ContextEngine

logger = logging.getLogger("modules.hydration")

class HydrationModule:
    """
    Módulo de Hidratação — Jarvis do Cerrado

    Responsável por:
    - Envio de lembretes motivacionais
    - Gerenciamento de fluxo interativo (sim/não/bebi)
    - Controle de estado (pausar/parar/retomar)
    - Logging de consumo
    """

    # Frases motivacionais variadas
    MOTIVATION_DRINK = [
        "Boa! Água entrando, foco voltando 💧",
        "Aí sim. Rim agradece, cérebro também 😄",
        "Perfeito. Postura ereta e mais um gole 👊",
        "Isso aí! Hidrata que o dia rende mais.",
        "Show! Menos uma pedra no rim, mais energia no corpo.",
        "Mandou bem. Água é vida!",
        "Excelente. O corpo agradece esse gole.",
    ]

    MOTIVATION_NUDGE = [
        "Uai… não esqueceu da água não, né?",
        "Ó o copo aí do lado te encarando 👀",
        "Levanta um tiquinho, estica e bebe água. Confia.",
        "Bora beber essa água aí, sô!",
        "Não deixa pra depois não, bebe um gole agora.",
        "Psiu... hora da água. 💧",
    ]

    MOTIVATION_GOAL_NEAR = [
        "Falta pouco agora! Última puxada 💪",
        "Tá quase lá. Hoje vai fechar bonito.",
        "Reta final! Só mais uns goles.",
        "Quase batendo a meta. Bora!",
    ]

    MOTIVATION_GOAL_HIT = [
        "Meta batida! Hoje você venceu a si mesmo 🏆",
        "Pode comemorar. Amanhã a gente repete o show.",
        "Sensacional! Hidratação nível máximo hoje.",
        "Fechou por hoje! Parabéns pela disciplina.",
    ]

    WELLNESS_TIPS = [
        "Já que levantou pra beber água, ajeita a postura aí 😄",
        "Bebeu água? Dá uma respirada funda também.",
        "Aproveita e estica as pernas um pouco.",
        "Dá uma piscada longa pra descansar os olhos também.",
    ]

    @staticmethod
    async def send_reminder(app, task: Dict[str, Any]):
        """
        Envia o lembrete de hidratação e ativa o fluxo de confirmação.
        """
        chat_id = task['chat_id']
        task_id = task['id']
        now = datetime.now(timezone.utc)

        # Recupera meta
        meta = json.loads(task.get('meta', '{}'))
        cup_ml = meta.get('cup_ml', 250)

        # Gera mensagem
        text = HydrationModule._generate_reminder_message(chat_id, cup_ml, now)

        # Salva contexto de fluxo
        # Isso permite que o usuário responda "sim", "ok", "bebi" para confirmar este lembrete
        flow_state = {
            "type": "hydration_confirm",
            "task_id": task_id,
            "cup_ml": cup_ml,
            "timestamp": now.isoformat()
        }
        ContextEngine.save_context(chat_id, {"flow": flow_state})

        # Envia mensagem
        reply_markup = None
        try:
            # Se possível, adicionar botões (InlineKeyboard) para facilitar
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = [
                [
                    InlineKeyboardButton(f"✅ Bebi ({cup_ml}ml)", callback_data="bebi agua"),
                    InlineKeyboardButton("❌ Agora não", callback_data="agora nao")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
        except Exception:
            # Se falhar import ou algo assim, segue sem botões
            pass

        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Erro ao enviar lembrete de hidratação: {e}")

    @staticmethod
    def handle_flow(chat_id: int, text: str, context: Dict) -> str:
        """
        Processa a resposta do usuário quando o fluxo de hidratação está ativo.
        """
        flow = context.get("flow")
        if not flow or flow["type"] != "hydration_confirm":
            return None

        t = text.lower().strip()
        task_id = flow.get("task_id")
        cup_ml = flow.get("cup_ml", 250)

        # Lista expandida de confirmações positivas
        positive_responses = [
            "sim", "ok", "beleza", "certo", "pode ser", "👍", "👌", "✔️", "bora",
            "bebi", "ta pago", "foi", "feito", "manda", "tomado", "já foi", "ja foi"
        ]

        # Lista expandida de cancelamentos/adiamentos
        negative_responses = [
            "não", "nao", "cancela", "deixa pra lá", "deixa pra la",
            "depois", "❌", "agora não", "agora nao", "espera"
        ]

        # Verifica resposta
        if any(x in t for x in positive_responses):
            # Limpa fluxo
            ContextEngine.save_context(chat_id, {"flow": None})
            return HydrationModule.log_intake(chat_id, cup_ml, task_id=task_id)

        elif any(x in t for x in negative_responses):
            # Limpa fluxo apenas, sem logar
            ContextEngine.save_context(chat_id, {"flow": None})
            return "Tranquilo. Quando der, cê bebe. Sem pressão."

        # Se não entendeu, mas está no fluxo, talvez seja melhor ignorar ou perguntar?
        # Regra de Ouro: "Nunca ser robótico".
        # Se o usuário falou algo nada a ver, assumimos que mudou de assunto e o Router vai tratar.
        # Mas o Router manda para cá primeiro se for "flow_input".
        # Vamos retornar None para indicar que não processamos, assim o Executor pode tentar outro handler ou fallback?
        # O Executor atual chama handle_response e devolve o resultado.
        # Vamos assumir que se não é sim nem não, não é confirmação.
        return None

    @staticmethod
    def log_intake(chat_id: int, amount_ml: int, task_id: int = None, manual: bool = False) -> str:
        """
        Registra consumo de água.
        """
        # Se não temos task_id, buscamos a ativa
        if not task_id:
            tasks = Persistence.get_tasks_by_action(chat_id, "hydration")
            if tasks:
                task_id = tasks[0]['id']
            else:
                # Cria task "tracker" oculta se não existir nenhuma ativa
                # (Isso garante que o log funcione mesmo sem lembretes ativos)
                now = datetime.now(timezone.utc)
                # Verifica se já existe um tracker hoje? Não, tasks são persistentes.
                # Vamos criar um tracker permanente se não houver.
                # Ou apenas logar numa task fantasma (id 0)? O FK constraints podem falhar.
                # Vamos criar uma task 'stopped' ou 'completed' apenas para referência?
                # Melhor: Recomendar ativar hidratação.
                # Mas o requisito diz: "Beber água sempre contabiliza, se hidratação ativa".
                # Se não está ativa (stopped), talvez devêssemos perguntar se quer reativar?
                # Vamos assumir que se o usuário chamou "log_intake" explicitamente, ele quer registrar.
                # Vamos buscar a última task mesmo que cancelada para usar de referência?
                last_task = Persistence.get_last_cancelled_task_by_action(chat_id, "hydration")
                if last_task:
                     task_id = last_task['id']
                else:
                     return "Hidratação não está configurada. Diga 'me lembre de beber água' para começar."

        # Loga interação
        Persistence.log_interaction(task_id, "confirm", str(amount_ml))

        # Dados para feedback
        total_today = Persistence.get_hydration_volume_today(chat_id)

        # Recupera meta da task
        # Precisamos ler a task do DB para saber a meta
        # (Idealmente cachearíamos isso, mas leitura de DB é rápida sqlite)
        # Se task_id é válido...
        # Como não temos um get_task_by_id exposto simples no Persistence (temos get_active...),
        # vamos usar o contexto da task atual se disponível ou padrão.
        # Simplificação: Meta padrão 2000 se não achar.
        meta_ml = 2000

        # Tenta pegar meta dos active tasks
        active_tasks = Persistence.get_tasks_by_action(chat_id, "hydration")
        if active_tasks:
             meta = json.loads(active_tasks[0].get('meta', '{}'))
             meta_ml = meta.get('meta_ml', 2000)

        # Feedback message
        if total_today >= meta_ml:
            # Verifica se ACABOU de bater a meta (interação atual fez passar)
            # Se antes estava < meta...
            prev_total = total_today - amount_ml
            if prev_total < meta_ml:
                return random.choice(HydrationModule.MOTIVATION_GOAL_HIT) + f" ({total_today}ml)"
            else:
                return f"Mais {amount_ml}ml pra conta! Total: {total_today}ml (Meta batida! 🏆)"

        elif total_today >= (meta_ml * 0.8):
             base = random.choice(HydrationModule.MOTIVATION_GOAL_NEAR)
             return f"{base} Total: {total_today}/{meta_ml}ml."

        else:
             base = random.choice(HydrationModule.MOTIVATION_DRINK)

             # Chance de dica de bem estar (10%)
             if random.random() < 0.1:
                 tip = random.choice(HydrationModule.WELLNESS_TIPS)
                 return f"{base} ({total_today}/{meta_ml}ml)\n\n💡 {tip}"

             return f"{base} ({total_today}/{meta_ml}ml)"

    @staticmethod
    def control_hydration(chat_id: int, command: str) -> str:
        """
        Gerencia comandos de controle: pausar, parar, retomar.
        """
        command = command.lower()
        tasks = Persistence.get_tasks_by_action(chat_id, "hydration")

        if "pausar" in command or "parar lembrete" in command or "silencio" in command:
            if not tasks:
                return "Não achei hidratação ativa pra pausar."

            for task in tasks:
                Persistence.update_task_status(task['id'], 'paused')

            return "Beleza, pausei os avisos. Mas continua bebendo, hein! 🥤"

        elif "parar hidratação" in command or "não quero mais" in command or "cancelar hidratação" in command:
            if not tasks:
                return "Hidratação já está parada."

            for task in tasks:
                Persistence.update_task_status(task['id'], 'cancelled')

            return "Certo, parei tudo. Quando quiser voltar, é só falar 'retomar hidratação'."

        elif "retomar" in command or "voltar" in command:
            # Verifica se já tem ativa
            if tasks:
                return "Uai, a hidratação já está ativa."

            # 1. Tenta encontrar PAUSADAS
            paused_tasks = Persistence.get_tasks_by_status(chat_id, "paused", "hydration")
            if paused_tasks:
                for task in paused_tasks:
                    # Reativa
                    Persistence.update_task_status(task['id'], 'active')
                    # Opcional: Ajustar next_run para agora se estiver muito atrasada?
                    # O Scheduler vai pegar se estiver atrasada.
                return "Hidratação retomada! Foco na meta. 💧"

            # 2. Tenta encontrar CANCELADAS (Paradas)
            last_task = Persistence.get_last_cancelled_task_by_action(chat_id, "hydration")

            if not last_task:
                 return "Não achei histórico recente. Que tal criar um novo? 'Me lembre de beber água'."

            # Recria a task baseada na última cancelada
            meta = json.loads(last_task.get('meta', '{}'))
            interval = last_task.get('interval_minutes', 60)
            text = last_task.get('text', 'Beber água')

            # Next run: Agora + intervalo
            next_run = datetime.now(timezone.utc) + timedelta(minutes=interval)

            Persistence.add_task(
                chat_id=chat_id,
                text=text,
                next_run=next_run,
                action="hydration",
                task_type="recurring",
                interval_minutes=interval,
                meta=meta,
                status="active"
            )

            return "Hidratação retomada! Foco na meta. 💧"

        return "Comando de hidratação não entendi."

    @staticmethod
    def update_config(chat_id: int, params: Dict[str, Any]) -> str:
        """
        Atualiza configurações da tarefa ativa de hidratação (Meta, Copo).
        """
        text = params.get("text", "").lower()
        val = params.get("value") # Capturado pelo regex se simples

        # 1. Encontrar tarefa ativa
        tasks = Persistence.get_tasks_by_action(chat_id, "hydration")
        if not tasks:
            return "Não achei nenhuma hidratação ativa pra corrigir. Que tal 'ativar hidratação'?"

        task = tasks[0]
        meta = json.loads(task.get('meta', '{}'))

        # 2. Interpretar o que mudar
        new_meta = meta.get("meta_ml", 2000)
        new_cup = meta.get("cup_ml", 250)
        changed = False

        # Parse value if not provided directly
        if not val:
            match = re.search(r'(\d+)\s*(l|ml|litros?)?', text)
            if match:
                num = int(match.group(1))
                unit = match.group(2)
                if unit and unit.lower().startswith('l'):
                    num *= 1000
                val = num

        if val:
            val = int(val)
            if "meta" in text or "total" in text:
                new_meta = val
                changed = True
                msg = f"Beleza, meta corrigida para {new_meta}ml."
            elif "copo" in text or "tamanho" in text:
                new_cup = val
                changed = True
                msg = f"Beleza, copo ajustado para {new_cup}ml."
            else:
                # Se não especificou, assume meta se for grande, copo se for pequeno?
                if val > 1000:
                    new_meta = val
                    changed = True
                    msg = f"Assumi que é a meta: {new_meta}ml."
                else:
                    new_cup = val
                    changed = True
                    msg = f"Assumi que é o copo: {new_cup}ml."
        else:
            return "Entendi que quer mudar, mas pra quanto? Fala tipo 'mudar meta pra 3000'."

        if changed:
            meta["meta_ml"] = new_meta
            meta["cup_ml"] = new_cup
            Persistence.update_task_meta(task['id'], meta)
            return msg

        return "Não entendi o que mudar."

    @staticmethod
    def get_status_message(chat_id: int) -> str:
        """
        Retorna status formatado.
        """
        total = Persistence.get_hydration_volume_today(chat_id)

        # Meta
        tasks = Persistence.get_tasks_by_action(chat_id, "hydration")
        meta_ml = 2000
        if tasks:
             meta = json.loads(tasks[0].get('meta', '{}'))
             meta_ml = meta.get('meta_ml', 2000)

        percentage = int((total / meta_ml) * 100)
        bars = "🟦" * (percentage // 10) + "⬜" * (10 - (percentage // 10))

        return (
            f"💧 Status Hidratação\n\n"
            f"{bars} {percentage}%\n"
            f"Total: {total}ml / {meta_ml}ml\n\n"
            f"Falta {max(0, meta_ml - total)}ml pra meta."
        )

    @staticmethod
    def _generate_reminder_message(chat_id: int, cup_ml: int, now: datetime) -> str:
        """
        Gera a mensagem do lembrete baseada no contexto (inércia, horário).
        """
        # Verifica inércia: Quantos lembretes sem confirmação hoje?
        # Podemos checar task_interactions 'confirm' vs 'last_run'?
        # Complexo. Vamos simplificar com aleatoriedade ponderada.

        message_type = "normal"
        if random.random() < 0.2: # 20% de chance de ser um 'nudge' se for tarde?
             message_type = "nudge"

        if message_type == "nudge":
             base = random.choice(HydrationModule.MOTIVATION_NUDGE)
             return f"{base}"
        else:
             # Normal reminder
             # Verifica se é dia ou noite
             # (Scheduler já cuida do horário de envio, mas texto pode adaptar)
             hour = (now.hour - 3) % 24
             if hour < 12:
                 greeting = "Bom dia!"
             elif hour < 18:
                 greeting = "Seguimos!"
             else:
                 greeting = "Noite boa."

             return f"💧 Hora de beber água ({cup_ml}ml). {greeting}"
