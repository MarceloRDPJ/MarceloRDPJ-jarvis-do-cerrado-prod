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
    for index, chunk in enumerate(message_chunks(text)):
        kwargs = {"reply_markup": reply_markup if index == 0 else None}
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        try:
            await message.reply_text(chunk, **kwargs)
        except BadRequest as e:
            logger.warning(f"Falha ao enviar com parse_mode; retry texto puro: {e}")
            try:
                kwargs.pop("parse_mode", None)
                await message.reply_text(plain_retry_text(chunk), **kwargs)
            except TelegramError as retry_error:
                logger.error(f"Falha ao enviar mensagem Telegram após retry: {retry_error}")
        except TelegramError as e:
            logger.error(f"Falha ao enviar mensagem Telegram: {e}")
