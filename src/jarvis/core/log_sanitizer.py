import re

_TELEGRAM_BOT_URL_RE = re.compile(r"bot\d+:[^/\s\"']+")


def sanitize_log_text(value: str) -> str:
    if not isinstance(value, str):
        return value
    return _TELEGRAM_BOT_URL_RE.sub("bot***TELEGRAM_TOKEN***", value)
