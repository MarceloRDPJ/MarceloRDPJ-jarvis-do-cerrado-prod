import re

def parse_minutes(text: str) -> int | None:
    """
    Extrai minutos de frases humanas.
    """
    patterns = [
        r"a cada (\d+) minuto",
        r"(\d+) minuto",
        r"(\d+) min"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))

    return None


def is_recurrent(text: str) -> bool:
    return "a cada" in text or "todo" in text
