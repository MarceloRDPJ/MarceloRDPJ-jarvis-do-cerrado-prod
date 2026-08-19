"""Watchdog do nó Android no GuardianService.

O Poco pode sumir por queda de Wi-Fi, bateria ou reinício. O Pi precisa avisar
uma única vez por transição e nunca reenviar comandos para o aparelho ausente.
"""

import pytest

from jarvis.services.guardian import GuardianService


class FakePocoService:
    def __init__(self, status):
        self._status = status

    def status(self):
        return self._status


def build_guardian(monkeypatch, status, enabled=True):
    sent = []

    class FakeBot:
        async def send_message(self, chat_id, text):
            sent.append(text)

    application = type("App", (), {"bot": FakeBot()})()
    guardian = GuardianService(application, chat_id=1)

    from jarvis.config import Config

    monkeypatch.setattr(Config, "POCO_NODE_ENABLED", enabled, raising=False)

    import jarvis.api.app as api_app

    monkeypatch.setattr(api_app, "get_poco_service", lambda: FakePocoService(status))
    return guardian, sent


@pytest.mark.asyncio
async def test_alerts_once_after_repeated_misses(monkeypatch):
    status = {"online": False, "heartbeat": {"node_id": "poco", "received_at": 1}}
    guardian, sent = build_guardian(monkeypatch, status)

    for _ in range(5):
        await guardian.check_poco_node()

    assert len(sent) == 1
    assert "heartbeat" in sent[0]
    assert guardian.poco_state == "offline"


@pytest.mark.asyncio
async def test_stays_quiet_before_the_third_miss(monkeypatch):
    status = {"online": False, "heartbeat": {"node_id": "poco", "received_at": 1}}
    guardian, sent = build_guardian(monkeypatch, status)

    await guardian.check_poco_node()
    await guardian.check_poco_node()

    assert sent == []


@pytest.mark.asyncio
async def test_never_alerts_for_a_node_that_never_reported(monkeypatch):
    """Sem heartbeat algum não houve queda; anunciar isso seria inventar um fato."""
    guardian, sent = build_guardian(monkeypatch, {"online": False, "heartbeat": None})

    for _ in range(5):
        await guardian.check_poco_node()

    assert sent == []
    assert guardian.poco_state == "unknown"


@pytest.mark.asyncio
async def test_blames_the_pi_network_instead_of_the_node(monkeypatch):
    status = {"online": False, "heartbeat": {"node_id": "poco", "received_at": 1}}
    guardian, sent = build_guardian(monkeypatch, status)
    guardian.internet_state = "offline"

    for _ in range(5):
        await guardian.check_poco_node()

    assert sent == []


@pytest.mark.asyncio
async def test_announces_recovery_once_and_reports_queued_results(monkeypatch):
    status = {"online": False, "heartbeat": {"node_id": "poco", "received_at": 1}}
    guardian, sent = build_guardian(monkeypatch, status)
    for _ in range(3):
        await guardian.check_poco_node()

    status["online"] = True
    status["heartbeat"] = {"node_id": "poco", "received_at": 2, "pending_results": 2}
    await guardian.check_poco_node()
    await guardian.check_poco_node()

    assert len(sent) == 2
    assert "voltou a responder" in sent[1]
    assert "2 resultado" in sent[1]
    assert guardian.poco_state == "online"


@pytest.mark.asyncio
async def test_disabled_node_is_not_monitored(monkeypatch):
    status = {"online": False, "heartbeat": {"node_id": "poco", "received_at": 1}}
    guardian, sent = build_guardian(monkeypatch, status, enabled=False)

    for _ in range(5):
        await guardian.check_poco_node()

    assert sent == []
