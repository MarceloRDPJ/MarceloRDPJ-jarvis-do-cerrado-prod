import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List

from jarvis.config import Config
from jarvis.tools.rss_reader import read_feeds
from jarvis.tools.web_fetch import fetch_url

logger = logging.getLogger(__name__)


@dataclass
class CurrentInfoResult:
    ok: bool
    source: str
    context: str = ""
    answer: str = ""
    error: str = ""


CURRENT_MARKERS = (
    "hoje", "agora", "atual", "ultima", "última", "noticias", "notícias",
    "tabela", "placar", "resultado", "preco", "preço", "cotacao", "cotação",
    "clima", "previsao", "previsão", "quando e", "quando é", "dia das maes",
    "dia das mães", "dia dos pais", "versao atual", "versão atual", "brasileirao", "brasileirão",
)


class CurrentInfo:
    def is_current_question(self, text: str) -> bool:
        return any(marker in text for marker in CURRENT_MARKERS)

    def collect(self, text: str) -> CurrentInfoResult:
        if "dia das maes" in text or "dia das mães" in text:
            return CurrentInfoResult(ok=True, source="local_calendar", answer=self._mothers_day())
        if "dia dos pais" in text:
            return CurrentInfoResult(ok=True, source="local_calendar", answer=self._fathers_day())
        if not Config.LOCAL_WEB_TOOLS_ENABLED:
            return CurrentInfoResult(ok=False, source="disabled", error="Ferramentas locais de internet desabilitadas.")
        if "noticias" in text or "notícias" in text:
            return self._news()
        if "cotacao" in text or "cotação" in text or "dolar" in text or "dólar" in text:
            return self._usd_quote()
        if "clima" in text or "previsao" in text or "previsão" in text:
            return self._weather(text)
        if "versao atual" in text or "versão atual" in text or "python" in text:
            return self._python_version()
        if "brasileirao" in text or "brasileirão" in text or "tabela" in text:
            return self._brasileirao()
        return CurrentInfoResult(ok=False, source="no_source", error="Não há fonte local configurada para essa pergunta atual.")

    def _news(self) -> CurrentInfoResult:
        items = read_feeds(limit=5)
        if not items:
            return CurrentInfoResult(ok=False, source="rss", error="Nenhum RSS configurado ou disponível para notícias.")
        lines = ["Notícias via RSS configurado:"]
        for item in items:
            lines.append(f"- {item.title}\n  Data: {item.published}\n  Link: {item.link}\n  Resumo: {self._strip_html(item.summary)[:300]}")
        return CurrentInfoResult(ok=True, source="rss", context="\n".join(lines))

    def _usd_quote(self) -> CurrentInfoResult:
        result = fetch_url("https://economia.awesomeapi.com.br/json/last/USD-BRL")
        if not result.ok:
            return CurrentInfoResult(ok=False, source="awesomeapi", error=f"Não consegui consultar cotação: {result.error}")
        try:
            data = json.loads(result.text).get("USDBRL", {})
        except json.JSONDecodeError:
            return CurrentInfoResult(ok=False, source="awesomeapi", error="Resposta de cotação inválida.")
        context = (
            "Cotação USD-BRL via API pública gratuita AwesomeAPI:\n"
            f"Compra: {data.get('bid')}\nVenda: {data.get('ask')}\n"
            f"Alta: {data.get('high')}\nBaixa: {data.get('low')}\nAtualizado: {data.get('create_date')}"
        )
        return CurrentInfoResult(ok=True, source="awesomeapi", context=context)

    def _weather(self, text: str) -> CurrentInfoResult:
        city = self._extract_weather_city(text) or "Goiania"
        result = fetch_url(f"https://wttr.in/{city}?format=j1&lang=pt")
        if not result.ok:
            return CurrentInfoResult(ok=False, source="wttr.in", error=f"Não consegui consultar clima: {result.error}")
        try:
            data = json.loads(result.text)
            current = data.get("current_condition", [{}])[0]
        except (json.JSONDecodeError, IndexError, TypeError):
            return CurrentInfoResult(ok=False, source="wttr.in", error="Resposta de clima inválida.")
        desc = current.get("lang_pt", [{}])[0].get("value") or current.get("weatherDesc", [{}])[0].get("value", "")
        context = (
            f"Clima atual via wttr.in para {city}:\n"
            f"Temperatura: {current.get('temp_C')}°C\nSensação: {current.get('FeelsLikeC')}°C\n"
            f"Condição: {desc}\nUmidade: {current.get('humidity')}%\nVento: {current.get('windspeedKmph')} km/h"
        )
        return CurrentInfoResult(ok=True, source="wttr.in", context=context)

    def _python_version(self) -> CurrentInfoResult:
        result = fetch_url("https://www.python.org/downloads/")
        if not result.ok:
            return CurrentInfoResult(ok=False, source="python.org", error=f"Não consegui consultar python.org: {result.error}")
        match = re.search(r"Download Python ([0-9]+\.[0-9]+\.[0-9]+)", result.text)
        if not match:
            return CurrentInfoResult(ok=False, source="python.org", error="Não consegui identificar a versão atual na página.")
        return CurrentInfoResult(ok=True, source="python.org", context=f"python.org informa como download principal: Python {match.group(1)}")

    def _brasileirao(self) -> CurrentInfoResult:
        if not Config.CURRENT_INFO_BRASILEIRAO_URL:
            return CurrentInfoResult(ok=False, source="brasileirao_config", error="Nenhuma fonte leve foi configurada para tabela do Brasileirão.")
        result = fetch_url(Config.CURRENT_INFO_BRASILEIRAO_URL)
        if not result.ok:
            return CurrentInfoResult(ok=False, source="brasileirao_config", error=f"Fonte da tabela indisponível: {result.error}")
        return CurrentInfoResult(ok=True, source="brasileirao_config", context=f"Conteúdo coletado da fonte configurada para Brasileirão:\n{self._strip_html(result.text)[:4000]}")

    def _mothers_day(self) -> str:
        current_year = date.today().year
        day = self._nth_weekday(current_year, 5, 6, 2)
        return f"No Brasil, o Dia das Mães em {current_year} cai em {day:%d/%m/%Y}. É comemorado no segundo domingo de maio."

    def _fathers_day(self) -> str:
        current_year = date.today().year
        day = self._nth_weekday(current_year, 8, 6, 2)
        return f"No Brasil, o Dia dos Pais em {current_year} cai em {day:%d/%m/%Y}. É comemorado no segundo domingo de agosto."

    def _nth_weekday(self, year: int, month: int, weekday: int, n: int) -> date:
        day = date(year, month, 1)
        while day.weekday() != weekday:
            day += timedelta(days=1)
        return day + timedelta(days=7 * (n - 1))

    def _strip_html(self, text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text or "")
        return re.sub(r"\s+", " ", text).strip()

    def _extract_weather_city(self, text: str) -> str:
        match = re.search(r"(?:clima|previsao|previsão)\s+(?:em|de|para)\s+([a-z0-9\- ]+)", text)
        return match.group(1).strip().replace(" ", "+") if match else ""
