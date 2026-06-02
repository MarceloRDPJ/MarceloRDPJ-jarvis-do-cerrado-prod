from jarvis.main import sanitize_log_text


def test_sanitize_telegram_bot_url_pattern():
    text = "GET https://api.telegram.org/bot123456:ABCdef-SECRET_token/getUpdates"

    sanitized = sanitize_log_text(text)

    assert "123456:ABCdef-SECRET_token" not in sanitized
    assert "bot***TELEGRAM_TOKEN***" in sanitized
