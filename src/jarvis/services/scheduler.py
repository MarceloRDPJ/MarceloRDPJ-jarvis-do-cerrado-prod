import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from jarvis.database.persistence import Persistence
from jarvis.modules.reminders import get_reminder_message
from jarvis.modules.hydration import HydrationModule

logger = logging.getLogger("services.scheduler")

class SchedulerService:
    """
    SchedulerService — Coração do sistema de lembretes.

    Responsabilidades:
    - Loop infinito verificando tarefas vencidas (Persistence)
    - Execução de tarefas (Envio de msg via Telegram)
    - Reagendamento de tarefas recorrentes
    - Lógica de "Madrugada" (Silêncio)
    """

    def __init__(self, application, interval_seconds: int = 30):
        self.app = application
        self.interval = interval_seconds
        self.running = False

    async def start(self):
        if self.running:
            return

        self.running = True
        logger.info("⏰ SchedulerService iniciado.")

        while self.running:
            try:
                await self.run_cycle()
            except Exception:
                logger.exception("Erro no ciclo do Scheduler")

            await asyncio.sleep(self.interval)

    async def run_cycle(self):
        now = datetime.now(timezone.utc)

        # 1. Busca tarefas vencidas
        tasks = Persistence.get_active_tasks_due(now)

        if not tasks:
            return

        logger.info(f"Scheduler: {len(tasks)} tarefas para processar.")

        for task in tasks:
            await self.process_task(task, now)

    async def process_task(self, task: Dict, now: datetime):
        chat_id = task['chat_id']
        task_id = task['id']
        action = task.get('action')

        # === 1. QUIET HOURS (08:00 - 19:00) para Hidratação ===
        if action == 'hydration':
            # Converte para local time (UTC-3)
            local_now = now - timedelta(hours=3)
            hour = local_now.hour

            # Se for antes das 08h ou depois das 19h
            if hour < 8 or hour >= 19:
                logger.info(f"Tarefa {task_id} (Hidratação) pausada (Quiet Hours). Reagendando...")

                # Se for recorrente, reagenda para o próximo dia às 08:00 ou mantém o intervalo se cair dentro
                # Simples: Reagenda para amanhã às 08:00 se passou das 19h
                # Se for madrugada (ex: 03h), reagenda para hoje às 08:00

                target_date = local_now.replace(minute=0, second=0, microsecond=0)
                if hour >= 19:
                    target_date += timedelta(days=1)
                    target_date = target_date.replace(hour=8)
                elif hour < 8:
                    target_date = target_date.replace(hour=8)

                # Converte de volta para UTC para salvar
                next_run_utc = target_date + timedelta(hours=3)

                Persistence.update_task_next_run(task_id, next_run_utc)
                return

            # Delega envio para o Módulo de Hidratação
            await HydrationModule.send_reminder(self.app, task)

            # Pula passo 2 e vai para reagendamento
            # (Poderíamos retornar aqui se HydrationModule lidasse com reagendamento,
            # mas o Scheduler é quem gerencia o tempo. Então continuamos para o passo 3)

        else:
            # === 2. Envio da Mensagem (Genérico) ===
            message = get_reminder_message(task, now)
            try:
                await self.app.bot.send_message(chat_id=chat_id, text=message)
            except Exception as e:
                logger.error(f"Falha ao enviar lembrete {task_id}: {e}")
                return # Não reagenda em caso de falha de transporte

        # === 3. Reagendamento ===
        if task['type'] == 'recurring':
            interval = task['interval_minutes']
            next_run = now + timedelta(minutes=interval)

            # Se a próxima execução cair no período de silêncio (hidratação),
            # já ajusta para o dia seguinte?
            # Não, deixa o check acima (Quiet Hours) lidar com isso na próxima execução.
            # Isso mantém a lógica simples.

            Persistence.update_task_next_run(task_id, next_run)
            logger.info(f"Tarefa {task_id} reagendada para {next_run}")
        else:
            Persistence.update_task_status(task_id, 'completed')
            logger.info(f"Tarefa {task_id} concluída.")

    def check_madrugada(self, now: datetime) -> bool:
        # Horário local aproximado (UTC-3 para Brasil/Cerrado)
        local_hour = (now.hour - 3) % 24
        return 23 <= local_hour or local_hour < 6
