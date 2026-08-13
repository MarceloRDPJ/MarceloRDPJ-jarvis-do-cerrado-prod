import json

import pytest

from jarvis.services.poco_node import PocoAuthenticationError, PocoNodeService


def test_signed_request_and_expiration(tmp_path):
    now = [1_700_000_000]
    service = PocoNodeService(tmp_path / "poco.json", "secret", clock=lambda: now[0])
    body = b'{"node_id":"poco"}'
    timestamp = str(now[0])
    signature = service.signature("secret", timestamp, "POST", "/api/poco/heartbeat", body)
    service.authenticate(timestamp, signature, "POST", "/api/poco/heartbeat", body)

    now[0] += 121
    with pytest.raises(PocoAuthenticationError):
        service.authenticate(timestamp, signature, "POST", "/api/poco/heartbeat", body)


def test_queue_is_persistent_and_idempotent(tmp_path):
    path = tmp_path / "poco.json"
    service = PocoNodeService(path, "secret")
    created = service.enqueue("device_status", {"detail": "basic"})
    accepted = service.next_job()
    assert accepted.job_id == created.job_id
    assert accepted.status == "accepted"

    running = service.update_job(created.job_id, "running")
    assert running.status == "running"
    completed = service.update_job(created.job_id, "completed", {"battery_level": 80})
    assert completed.result == {"battery_level": 80}
    assert service.update_job(created.job_id, "failed", error="late").status == "completed"

    restored = PocoNodeService(path, "secret")
    assert restored.status()["queued_jobs"] == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["jobs"][0]["status"] == "completed"


def test_rejects_arbitrary_actions(tmp_path):
    service = PocoNodeService(tmp_path / "poco.json", "secret")
    with pytest.raises(ValueError):
        service.enqueue("shell", {"command": "anything"})


def test_heartbeat_is_sanitized_and_becomes_stale(tmp_path):
    now = [1000]
    service = PocoNodeService(tmp_path / "poco.json", "secret", heartbeat_stale_seconds=10, clock=lambda: now[0])
    service.record_heartbeat(
        {
            "node_id": "poco-x3",
            "battery_level": 500,
            "battery_temperature_c": 32.5,
            "thermal_status": "none",
            "wifi_connected": True,
            "agent_version": "0.1",
            "ignored_secret": "must-not-persist",
        }
    )
    assert service.status()["online"] is True
    persisted = (tmp_path / "poco.json").read_text(encoding="utf-8")
    assert "ignored_secret" not in persisted
    assert service.status()["heartbeat"]["battery_level"] == 100
    now[0] += 11
    assert service.status()["online"] is False
