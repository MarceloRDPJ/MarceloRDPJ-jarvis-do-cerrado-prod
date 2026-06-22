from datetime import datetime, timezone, timedelta

import pytest

from jarvis.core.events import Event
from jarvis.database.persistence import Persistence
from jarvis.services.energy import EnergyService


def test_event_timestamp_is_timezone_aware_utc():
    event = Event(type="test.utc", source="test", payload={})
    parsed = datetime.fromisoformat(event.timestamp)

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


def test_energy_sample_is_persisted_as_event(monkeypatch):
    monkeypatch.setattr(EnergyService, "_estimate_current_watts", lambda: 4.2)

    EnergyService.log_energy_sample()

    events = Persistence.get_events_by_type("energy.sample", limit=10)
    assert len(events) == 1
    assert events[0]["source"] == "energy"
    assert events[0]["payload"]["watts"] == 4.2


def test_get_events_by_type_filters_since():
    old_event = Event(
        type="energy.sample",
        source="test",
        payload={"watts": 1},
        timestamp=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
    )
    new_event = Event(type="energy.sample", source="test", payload={"watts": 2})
    Persistence.log_event(old_event)
    Persistence.log_event(new_event)

    events = Persistence.get_events_by_type(
        "energy.sample",
        since=datetime.now(timezone.utc) - timedelta(days=1),
    )

    assert [event["payload"]["watts"] for event in events] == [2]


@pytest.mark.asyncio
async def test_api_recent_events_reads_events_not_snapshots():
    from jarvis.api.app import get_recent_events

    Persistence.save_snapshot({"timestamp": datetime.now(timezone.utc).isoformat(), "fake": "snapshot"})
    event = Event(type="system.real", source="test", payload={"ok": True})
    Persistence.log_event(event)

    response = await get_recent_events(limit=10)

    assert len(response["events"]) == 1
    assert response["events"][0]["id"] == event.id
    assert "fake" not in response["events"][0]


@pytest.mark.asyncio
async def test_health_reports_degraded_when_optional_llm_unavailable(monkeypatch):
    from jarvis.api import app as api_app
    from jarvis.core.llm_fallback import LLMFallbackEngine

    monkeypatch.setattr(LLMFallbackEngine, "is_available", lambda self: False)

    response = await api_app.get_system_health()

    assert response["checks"]["database"]["ok"] is True
    assert response["checks"]["local_llm"]["required"] is False
    assert response["status"] == "degraded"


@pytest.mark.asyncio
async def test_mcp_resource_endpoint_reads_resource(monkeypatch):
    from types import SimpleNamespace
    from jarvis.api import app as api_app

    async def get_resource(uri):
        return {"uri": uri, "data": {"ok": True}}

    monkeypatch.setattr(api_app, "get_service", lambda name: SimpleNamespace(get_resource=get_resource))

    response = await api_app.get_mcp_resource("jarvis://system/status")

    assert response["uri"] == "jarvis://system/status"
    assert response["data"]["ok"] is True
