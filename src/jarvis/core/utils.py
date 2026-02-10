import asyncio
import logging
import random
from functools import wraps
from datetime import datetime
from jarvis.config import Config

logger = logging.getLogger(__name__)

def retry_with_backoff(retries=None, delay=None):
    """
    Decorator para retry automático com exponential backoff.
    Lê defaults do config.yaml se não passados.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Carrega config se não definido
            max_retries = retries or Config.get('system.retry_attempts', 3)
            base_delay = delay or Config.get('system.retry_delay', 2)

            attempt = 0
            last_exception = None

            while attempt < max_retries:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    last_exception = e
                    wait_time = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    logger.warning(f"⚠️ Erro em {func.__name__}: {e}. Tentativa {attempt}/{max_retries}. Esperando {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)

            logger.error(f"❌ Falha definitiva em {func.__name__} após {max_retries} tentativas.")
            raise last_exception
        return wrapper
    return decorator

def is_quiet_hours(now_local: datetime, quiet_hours: dict) -> bool:
    """
    Verifica se o horário atual está dentro do intervalo de silêncio.
    Suporta intervalos que cruzam a meia-noite (ex: 22:00 -> 08:00).
    """
    try:
        start_str = quiet_hours.get("start", "22:00")
        end_str = quiet_hours.get("end", "08:00")

        start = datetime.strptime(start_str, "%H:%M").time()
        end = datetime.strptime(end_str, "%H:%M").time()

        now_time = now_local.time()

        if start < end:
            return start <= now_time < end
        else:
            # Cruza meia-noite
            return now_time >= start or now_time < end
    except Exception as e:
        logger.error(f"Erro ao verificar quiet_hours: {e}")
        return False
