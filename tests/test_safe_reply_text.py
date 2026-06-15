from unittest.mock import AsyncMock

import pytest

from jarvis.core.telegram_safe import safe_reply_text


@pytest.mark.asyncio
async def test_safe_reply_text_sends_plain_text_without_parse_mode():
    message = AsyncMock()

    await safe_reply_text(message, "LLM local: disponível\nEndpoint/CLI: /tmp/model.gguf")

    message.reply_text.assert_called_once()
    assert "parse_mode" not in message.reply_text.call_args.kwargs


@pytest.mark.asyncio
async def test_safe_reply_text_retries_without_parse_mode_on_bad_request():
    message = AsyncMock()
    message.reply_text.side_effect = [Exception("Can't parse entities"), None]

    await safe_reply_text(message, "texto *quebrado*", parse_mode="Markdown")

    assert message.reply_text.call_count == 2
    assert "parse_mode" not in message.reply_text.call_args_list[1].kwargs
