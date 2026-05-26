from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jarvis.core.reminder_callbacks import ReminderCallbacks
from jarvis.core.context import ContextEngine
from jarvis.core.flows import RemindersFlow
from jarvis.database.persistence import Persistence
from jarvis.services.scheduler import SchedulerService


@pytest.mark.asyncio
async def test_unique_reminder_is_delivered_not_completed():
    chat_id = 123
    task_id = Persistence.add_task(
        chat_id=chat_id,
        text="Enviar documento",
        next_run=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    scheduler = SchedulerService(app, interval_seconds=30)

    task = Persistence.get_task(task_id)
    await scheduler.process_task(task, datetime.now(timezone.utc))

    updated = Persistence.get_task(task_id)
    assert updated["status"] == "delivered"
    assert Persistence.get_active_tasks_due(datetime.now(timezone.utc)) == []


@pytest.mark.asyncio
async def test_snooze_reactivates_delivered_reminder():
    chat_id = 123
    task_id = Persistence.add_task(
        chat_id=chat_id,
        text="Pagar boleto",
        next_run=datetime.now(timezone.utc) - timedelta(minutes=1),
        status="delivered",
    )
    query = SimpleNamespace(edit_message_text=AsyncMock())

    await ReminderCallbacks.handle_snooze(task_id, chat_id, 15, query)

    updated = Persistence.get_task(task_id)
    assert updated["status"] == "active"
    assert datetime.fromisoformat(updated["next_run"]) > datetime.now(timezone.utc)
    query.edit_message_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_done_validates_task_owner():
    task_id = Persistence.add_task(
        chat_id=123,
        text="Comprar pão",
        next_run=datetime.now(timezone.utc),
        status="delivered",
    )
    query = SimpleNamespace(edit_message_text=AsyncMock())

    await ReminderCallbacks.handle_done(task_id, 999, query)

    updated = Persistence.get_task(task_id)
    assert updated["status"] == "delivered"
    query.edit_message_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_done_completes_owned_reminder_and_logs_interaction():
    chat_id = 123
    task_id = Persistence.add_task(
        chat_id=chat_id,
        text="Comprar remédio",
        next_run=datetime.now(timezone.utc),
        status="delivered",
    )
    query = SimpleNamespace(edit_message_text=AsyncMock())

    await ReminderCallbacks.handle_done(task_id, chat_id, query)

    updated = Persistence.get_task(task_id)
    assert updated["status"] == "completed"
    interactions = Persistence.get_task_interactions(task_id)
    assert any(i["interaction_type"] == "done" for i in interactions)


@pytest.mark.asyncio
async def test_reschedule_callback_starts_flow_and_response_updates_task():
    chat_id = 123
    task_id = Persistence.add_task(
        chat_id=chat_id,
        text="Enviar tarefa",
        next_run=datetime.now(timezone.utc),
        status="delivered",
    )
    query = SimpleNamespace(edit_message_text=AsyncMock())

    await ReminderCallbacks.handle_reschedule_request(task_id, chat_id, query)
    ctx = ContextEngine.get_context(chat_id)
    assert ctx["flow"]["type"] == "reminder_reschedule"

    resp = RemindersFlow.handle_reschedule_response(chat_id, "amanhã às 9h", ctx)
    assert "Remarquei" in resp
    assert Persistence.get_task(task_id)["status"] == "active"


@pytest.mark.asyncio
async def test_nagging_unique_reminder_stays_active():
    chat_id = 123
    task_id = Persistence.add_task(
        chat_id=chat_id,
        text="Tomar remédio",
        next_run=datetime.now(timezone.utc) - timedelta(minutes=1),
        meta={"nag": True, "nag_interval_minutes": 10, "priority": "urgent"},
    )
    app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    scheduler = SchedulerService(app, interval_seconds=30)

    await scheduler.process_task(Persistence.get_task(task_id), datetime.now(timezone.utc))

    updated = Persistence.get_task(task_id)
    assert updated["status"] == "active"
    assert datetime.fromisoformat(updated["next_run"]) > datetime.now(timezone.utc)
