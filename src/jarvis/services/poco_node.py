"""Reliable, signed job queue for the dedicated Android node."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# Only actions the agent really implements. Advertising more meant the job was
# queued, dispatched and only rejected by the phone after the full timeout.
ALLOWED_ACTIONS = frozenset(
    {
        "device_status",
        "network_check",
        "read_bill_cache",
        "refresh_equatorial_bills",
        "refresh_saneago_bills",
    }
)

TERMINAL_STATES = frozenset({"completed", "failed", "expired"})


@dataclass
class PocoJob:
    job_id: str
    action: str
    params: dict[str, Any]
    created_at: float
    expires_at: float
    status: str = "queued"
    updated_at: float = field(default_factory=time.time)
    result: dict[str, Any] | None = None
    error: str | None = None
    attempts: int = 0


class PocoAuthenticationError(ValueError):
    pass


class PocoNodeService:
    """Small persistent queue. It never exposes arbitrary command execution."""

    def __init__(
        self,
        storage_path: str | os.PathLike,
        shared_secret: str = "",
        signature_max_age_seconds: int = 120,
        heartbeat_stale_seconds: int = 150,
        lease_seconds: int = 60,
        max_attempts: int = 3,
        clock=time.time,
    ):
        self.storage_path = Path(storage_path)
        self.shared_secret = shared_secret
        self.signature_max_age_seconds = signature_max_age_seconds
        self.heartbeat_stale_seconds = heartbeat_stale_seconds
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.clock = clock
        self._lock = threading.RLock()
        self._jobs: dict[str, PocoJob] = {}
        self._heartbeat: dict[str, Any] | None = None
        self._load()

    @staticmethod
    def signature(secret: str, timestamp: str, method: str, path: str, body: bytes) -> str:
        body_hash = hashlib.sha256(body).hexdigest()
        canonical = f"{timestamp}\n{method.upper()}\n{path}\n{body_hash}".encode()
        return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()

    def authenticate(
        self,
        timestamp: str | None,
        signature: str | None,
        method: str,
        path: str,
        body: bytes,
    ) -> None:
        if not self.shared_secret:
            raise PocoAuthenticationError("Poco node secret is not configured")
        if not timestamp or not signature:
            raise PocoAuthenticationError("Missing Poco authentication headers")
        try:
            sent_at = int(timestamp)
        except ValueError as exc:
            raise PocoAuthenticationError("Invalid Poco timestamp") from exc
        if abs(self.clock() - sent_at) > self.signature_max_age_seconds:
            raise PocoAuthenticationError("Expired Poco request")
        expected = self.signature(self.shared_secret, timestamp, method, path, body)
        if not hmac.compare_digest(expected, signature):
            raise PocoAuthenticationError("Invalid Poco signature")

    def enqueue(self, action: str, params: dict[str, Any] | None = None, ttl_seconds: int = 180) -> PocoJob:
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported Poco action: {action}")
        now = self.clock()
        job = PocoJob(
            job_id=uuid.uuid4().hex,
            action=action,
            params=params or {},
            created_at=now,
            expires_at=now + max(10, min(ttl_seconds, 900)),
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._save()
        return job

    def next_job(self) -> PocoJob | None:
        now = self.clock()
        with self._lock:
            changed = self._sweep(now)
            for job in sorted(self._jobs.values(), key=lambda item: item.created_at):
                if job.status == "queued":
                    job.status = "accepted"
                    job.attempts += 1
                    job.updated_at = now
                    self._save()
                    return job
            if changed:
                self._save()
        return None

    def _sweep(self, now: float) -> bool:
        """Expire dead jobs and return abandoned leases to the queue.

        A job goes to ``accepted`` the moment it is handed out. If the Wi-Fi drops
        exactly then, the node never sees it and the job would sit there until the
        TTL while the user waits. Handing it back after the lease gives the node a
        second chance inside the same request. The agent deduplicates by ``job_id``,
        so a redelivered job is never executed twice.
        """
        changed = False
        for job in self._jobs.values():
            if job.status in {"queued", "accepted", "running"} and job.expires_at <= now:
                job.status = "expired"
                job.updated_at = now
                changed = True
            elif job.status == "accepted" and now - job.updated_at > self.lease_seconds:
                if job.attempts >= self.max_attempts:
                    job.status = "failed"
                    job.error = "O Poco não confirmou o início da tarefa"
                else:
                    job.status = "queued"
                job.updated_at = now
                changed = True
        return changed

    def get_job(self, job_id: str) -> PocoJob | None:
        """Return a detached snapshot so callers cannot mutate queue state."""
        with self._lock:
            job = self._jobs.get(job_id)
            return PocoJob(**asdict(job)) if job else None

    def update_job(
        self,
        job_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> PocoJob:
        if status not in {"running", "completed", "failed"}:
            raise ValueError("Invalid Poco job state")
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            if job.status in TERMINAL_STATES:
                return job
            allowed = {
                # A lease can be requeued while the node is still working on it; its
                # durable outbox will report the real outcome, so accept it here
                # instead of answering 4xx and making the node drop a real result.
                "queued": {"running", "completed", "failed"},
                "accepted": {"running", "completed", "failed"},
                "running": {"completed", "failed"},
            }
            if status not in allowed.get(job.status, set()):
                raise ValueError(f"Invalid transition: {job.status} -> {status}")
            job.status = status
            job.updated_at = self.clock()
            job.result = result if status == "completed" else None
            job.error = str(error)[:500] if error and status == "failed" else None
            self._save()
            return job

    def record_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe = {
            "node_id": str(payload.get("node_id", ""))[:64],
            "battery_level": self._number(payload.get("battery_level"), 0, 100),
            "battery_temperature_c": self._number(payload.get("battery_temperature_c"), -20, 90),
            "thermal_status": str(payload.get("thermal_status", "unknown"))[:32],
            "wifi_connected": bool(payload.get("wifi_connected", False)),
            "agent_version": str(payload.get("agent_version", ""))[:32],
            "saneago_configured": bool(payload.get("saneago_configured", False)),
            "equatorial_configured": bool(payload.get("equatorial_configured", False)),
            "water_units": int(self._number(payload.get("water_units"), 0, 8) or 0),
            "energy_units": int(self._number(payload.get("energy_units"), 0, 8) or 0),
            "busy": bool(payload.get("busy", False)),
            "pending_results": int(self._number(payload.get("pending_results"), 0, 999) or 0),
            "received_at": self.clock(),
        }
        with self._lock:
            self._heartbeat = safe
            self._save()
        return safe

    def status(self) -> dict[str, Any]:
        with self._lock:
            heartbeat = dict(self._heartbeat) if self._heartbeat else None
            queued = sum(1 for job in self._jobs.values() if job.status == "queued")
            running = sum(1 for job in self._jobs.values() if job.status in {"accepted", "running"})
        online = bool(
            heartbeat
            and self.clock() - float(heartbeat["received_at"]) <= self.heartbeat_stale_seconds
        )
        return {"online": online, "heartbeat": heartbeat, "queued_jobs": queued, "active_jobs": running}

    @staticmethod
    def _number(value: Any, minimum: float, maximum: float) -> float | None:
        try:
            return max(minimum, min(maximum, float(value)))
        except (TypeError, ValueError):
            return None

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._jobs = {item["job_id"]: PocoJob(**item) for item in data.get("jobs", [])}
            self._heartbeat = data.get("heartbeat")
        except (OSError, ValueError, TypeError, KeyError):
            self._jobs = {}
            self._heartbeat = None

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"jobs": [asdict(job) for job in self._jobs.values()], "heartbeat": self._heartbeat}
        temporary = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, self.storage_path)
