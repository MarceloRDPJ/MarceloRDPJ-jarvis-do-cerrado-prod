import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from jarvis.database.persistence import Persistence
from jarvis.modules.reminders import get_reminder_message

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
        is_madrugada = self.check_madrugada(now)

        # Lógica de Madrugada (Simplificada: Se for madrugada e não confirmado, segura?)
        # Por enquanto, vamos apenas alterar o tom da mensagem na função get_reminder_message
        # A lógica de "pausar automaticamente" exigiria analisar o histórico de interações (task_interactions)

        # Envia a mensagem
        message = get_reminder_message(task, now)
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=message)

            # Se for 'hydration', adicionar botões ou esperar resposta textual?
            # O requisito diz: "Respostas aceitas: 'bebi', 'ok'..." via texto.
            # Então apenas enviamos a mensagem.

        except Exception as e:
            logger.error(f"Falha ao enviar lembrete {task_id}: {e}")
            return # Não reagenda se falhou o envio? Ou reagenda para tentar depois?
                   # Melhor não reagendar recorrente se falhou transporte, mas aqui assumimos sucesso lógico.

        # Reagendamento
        if task['type'] == 'recurring':
            interval = task['interval_minutes']
            # next_run = agora + intervalo (para evitar acúmulo se o bot ficou desligado)
            # ou next_run = next_run original + intervalo (para manter cadência rigorosa)
            # O requisito diz: "proxima_execucao = agora + intervalo" (Scheduler e Execução)
            next_run = now + timedelta(minutes=interval)
            Persistence.update_task_next_run(task_id, next_run)
            logger.info(f"Tarefa {task_id} reagendada para {next_run}")
        else:
            # Tarefa única concluída
            Persistence.update_task_status(task_id, 'completed')
            logger.info(f"Tarefa {task_id} concluída.")

    def check_madrugada(self, now: datetime) -> bool:
        # Horário local aproximado (UTC-3 para Brasil/Cerrado)
        local_hour = (now.hour - 3) % 24
        return 23 <= local_hour or local_hour < 6
