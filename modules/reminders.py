import logging
from telegram.ext import ContextTypes

logger = logging.getLogger("modules.reminders")


# ===============================
# JOB EXECUTADO PELO TELEGRAM
# ===============================
async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data or {}

    text = data.get("text", "Lembrete")
    count = data.get("count", 0) + 1

    # Atualiza contador (memória curta do job)
    data["count"] = count
    job.data = data

    # Mensagem mais humana
    if count == 1:
        message = f"⏰ Ei! Hora de {text}."
    else:
        message = f"⏰ Lembrete ({count}x): {text}"

    await context.bot.send_message(
        chat_id=job.chat_id,
        text=message
    )


# ===============================
# REGISTRO DO JOB
# ===============================
def set_reminder_job(
    application,
    chat_id: int,
    text: str,
    minutes: int,
    repeat: bool = False,
    job_name: str | None = None
) -> str:
    """
    Cria um lembrete no JobQueue.

    Retorna o nome do job (ID lógico).
    """

    delay_seconds = minutes * 60

    # Nome único e previsível (essencial para cancelar depois)
    job_name = job_name or f"reminder_{chat_id}_{abs(hash(text))}"

    job_data = {
        "text": text,
        "count": 0,
        "repeat": repeat,
        "interval_minutes": minutes
    }

    # Remove job antigo com mesmo nome (idempotência)
    for job in application.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    if repeat:
        application.job_queue.run_repeating(
            reminder_job,
            interval=delay_seconds,
            first=delay_seconds,
            chat_id=chat_id,
            data=job_data,
            name=job_name
        )
        logger.info(f"Lembrete recorrente criado: {job_name}")
    else:
        application.job_queue.run_once(
            reminder_job,
            delay_seconds,
            chat_id=chat_id,
            data=job_data,
            name=job_name
        )
        logger.info(f"Lembrete único criado: {job_name}")

    return job_name


# ===============================
# CANCELAMENTO (PREPARADO)
# ===============================
def cancel_reminder(application, job_name: str) -> bool:
    jobs = application.job_queue.get_jobs_by_name(job_name)
    if not jobs:
        return False

    for job in jobs:
        job.schedule_removal()

    return True
