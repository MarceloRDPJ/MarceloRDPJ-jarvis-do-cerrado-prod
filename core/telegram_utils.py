import re

def escape_markdown(text: str) -> str:
    """
    Escapa caracteres problemáticos do Markdown do Telegram.
    Compatível com respostas técnicas.
    """
    if not text:
        return text

    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(
        f"([{re.escape(escape_chars)}])",
        r"\\\1",
        text
    )
