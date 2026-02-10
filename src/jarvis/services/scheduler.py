import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from jarvis.database.persistence import Persistence
from jarvis.modules.reminders import get_reminder_message
from jarvis.modules.hydration import HydrationModule
from jarvis.config import Config

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

    def __init__(self, application, interval_seconds: int = None):
        self.app = application
        self.interval = interval_seconds or Config.SCHEDULER_INTERVAL_SECONDS
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

        # === 1. HIDRATAÇÃO (Novo Sistema) ===
        if action in ['hydration', 'hydration_check']:
            # Delega TUDO para o módulo (Estado, Quiet Hours, Intervalo Dinâmico)
            await HydrationModule.check_schedule(self.app, task)

            # O Scheduler prossegue para o Reagendamento Padrão abaixo.
            # Se o módulo decidiu não enviar nada (Quiet Hours ou bebeu recente),
            # o Scheduler simplesmente agendará a próxima verificação para daqui a X minutos.
            # Isso mantém o "Heartbeat" vivo.

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
        # Horário local baseado na configuração
        local_now = now.astimezone(Config.TZ)
        local_hour = local_now.hour
        return 23 <= local_hour or local_hour < 6
