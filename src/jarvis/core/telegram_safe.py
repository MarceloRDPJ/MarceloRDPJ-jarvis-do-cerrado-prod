import logging
import re

try:
    from telegram.error import BadRequest, TelegramError
except Exception:  # pragma: no cover - protege ambiente de teste com pacote quebrado
    BadRequest = Exception
    TelegramError = Exception

logger = logging.getLogger(__name__)

TELEGRAM_TEXT_LIMIT = 3900


def message_chunks(text: str, limit: int = TELEGRAM_TEXT_LIMIT):
    text = str(text or "")
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return chunks or [""]


def plain_retry_text(text: str) -> str:
    return re.sub(r"[`*_\[\]()~>#=|{}.!-]", "", str(text or ""))


async def safe_reply_text(message, text, reply_markup=None, parse_mode=None):
    """Envia texto ao Telegram sem Markdown por padrão e nunca derruba o handler."""

    async def retry_as_plain_text(chunk, kwargs, error):
        logger.warning(f"Falha ao enviar com parse_mode; retry texto puro: {error}")
        try:
            kwargs.pop("parse_mode", None)
            await message.reply_text(plain_retry_text(chunk), **kwargs)
        except TelegramError as retry_error:
            logger.error(f"Falha ao enviar mensagem Telegram após retry: {retry_error}")

    for index, chunk in enumerate(message_chunks(text)):
        kwargs = {"reply_markup": reply_markup if index == 0 else None}
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        try:
            await message.reply_text(chunk, **kwargs)
        except BadRequest as e:
            await retry_as_plain_text(chunk, kwargs, e)
        except TelegramError as e:
            logger.error(f"Falha ao enviar mensagem Telegram: {e}")
        except Exception as e:
            # Alguns adaptadores/mocks não preservam BadRequest, mas mantêm a
            # mensagem oficial do Telegram. Só fazemos retry para esse caso.
            is_parse_error = parse_mode and "parse entit" in str(e).lower()
            if is_parse_error:
                await retry_as_plain_text(chunk, kwargs, e)
            else:
                logger.exception("Falha inesperada ao enviar mensagem Telegram")
