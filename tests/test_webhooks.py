from unittest.mock import AsyncMock, patch

import pytest

from jarvis.api.webhook_manager import WebhookManager


@pytest.mark.asyncio
async def test_webhook_logs_success_boolean():
    manager = WebhookManager()
    webhook = {
        "id": "wh1",
        "name": "Teste",
        "url": "http://example.local/webhook",
        "events": ["*"],
        "active": True,
        "secret": "",
        "success_count": 0,
        "fail_count": 0,
    }

    with patch("aiohttp.ClientSession.post") as mock_post:
        response = AsyncMock()
        response.status = 204
        response.text = AsyncMock(return_value="ok")
        mock_post.return_value.__aenter__.return_value = response

        await manager._send_webhook(webhook, "test", {"ok": True})

    logs = manager.get_logs(1)
    assert logs[0]["status"] == 204
    assert logs[0]["success"] is True
    assert webhook["success_count"] == 1
