import logging
from dataclasses import dataclass

import requests

from jarvis.config import Config

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    ok: bool
    url: str
    text: str = ""
    status_code: int = None
    error: str = ""


def fetch_url(url: str, timeout: int = None, max_chars: int = None) -> FetchResult:
    """Acessa uma URL pública com timeout, user-agent e limite de resposta."""
    if not Config.LOCAL_WEB_TOOLS_ENABLED:
        return FetchResult(ok=False, url=url, error="Ferramentas locais de internet desabilitadas.")

    timeout = timeout or Config.WEB_FETCH_TIMEOUT_SECONDS
    max_chars = max_chars or Config.WEB_FETCH_MAX_CHARS
    headers = {"User-Agent": Config.WEB_USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code >= 400:
            logger.warning(f"Web fetch bloqueado/falhou status={response.status_code} url={url}")
            return FetchResult(ok=False, url=url, status_code=response.status_code, error=f"HTTP {response.status_code}")
        response.encoding = response.encoding or "utf-8"
        return FetchResult(ok=True, url=url, text=response.text[:max_chars], status_code=response.status_code)
    except requests.exceptions.Timeout:
        logger.warning(f"Web fetch timeout url={url}")
        return FetchResult(ok=False, url=url, error="timeout")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Web fetch falhou url={url}: {e}")
        return FetchResult(ok=False, url=url, error=str(e))
