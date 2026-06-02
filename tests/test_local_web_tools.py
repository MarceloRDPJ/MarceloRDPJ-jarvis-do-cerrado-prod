from unittest.mock import MagicMock, patch

from jarvis.tools.current_info import CurrentInfo
from jarvis.tools.rss_reader import _parse_rss
from jarvis.tools.web_fetch import fetch_url


def test_fetch_url_uses_timeout_user_agent_and_limits_response():
    with patch("requests.get") as mock_get:
        response = MagicMock(status_code=200, text="abcdef", encoding="utf-8")
        mock_get.return_value = response

        result = fetch_url("https://example.com", timeout=3, max_chars=3)

    assert result.ok
    assert result.text == "abc"
    assert mock_get.call_args.kwargs["timeout"] == 3
    assert "User-Agent" in mock_get.call_args.kwargs["headers"]


def test_parse_rss_items():
    xml = """
    <rss><channel><item><title>Notícia</title><link>https://example.com</link>
    <pubDate>hoje</pubDate><description>Resumo</description></item></channel></rss>
    """

    items = _parse_rss(xml)

    assert len(items) == 1
    assert items[0].title == "Notícia"
    assert items[0].link == "https://example.com"


def test_current_info_mothers_day_local_rule():
    result = CurrentInfo().collect("quando e o dia das maes")

    assert result.ok
    assert result.source == "local_calendar"
    assert "segundo domingo de maio" in result.answer


def test_current_info_brasileirao_without_config_is_honest():
    result = CurrentInfo().collect("tabela do brasileirao")

    assert not result.ok
    assert result.source == "brasileirao_config"
    assert "Nenhuma fonte" in result.error
