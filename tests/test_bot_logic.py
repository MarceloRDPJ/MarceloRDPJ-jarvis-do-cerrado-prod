import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
import types

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from jarvis.core.brain import Brain
from jarvis.core.executor import Executor
from jarvis.config import Config
from jarvis.database.persistence import Persistence
from jarvis.core.events import Event
from jarvis.core.flows import RemindersFlow
from jarvis.core.context import ContextEngine

class TestHomeAssistantBot(unittest.IsolatedAsyncioTestCase):

    @patch('jarvis.core.brain.LocalBrainEngine')
    async def test_brain_process_intent_local(self, mock_local_brain_cls):
        # Configurar mock do LocalBrain
        mock_instance = mock_local_brain_cls.return_value
        mock_instance.process = AsyncMock(return_value={
            "text": "Luz ligada (simulação)",
            "confidence": 0.9,
            "source": "local_static"
        })

        brain = Brain()
        result = await brain.process_intent("Liga a luz da sala")

        self.assertIsInstance(result, dict)
        self.assertEqual(result['intent'], 'chat')
        self.assertEqual(result['source'], 'local_brain')

    @patch('jarvis.modules.network.send_magic_packet')
    @patch('jarvis.core.utils.asyncio.sleep')
    async def test_executor_wol_retry(self, mock_sleep, mock_send_magic):
        mock_send_magic.side_effect = [Exception("Fail 1"), None]

        Config.PC_MAC = "AA:BB:CC:DD:EE:FF"
        app = MagicMock()
        Executor(app)
        pass

    async def test_executor_reminder_persistence(self):
        # Updated test to use RemindersFlow manually since Executor triggers flow

        chat_id = 123
        data = {
            "text": "Teste DB",
            "minutes": 5,
            "repeat": True,
            "action_type": "default"
        }

        # Simulate final step of flow
        RemindersFlow.finalize_creation(chat_id, data)

        tasks = Persistence.get_active_tasks(123)
        found = any(t["text"] == "Teste DB" for t in tasks)
        self.assertTrue(found)

    async def test_reminder_list_delete_button_uses_explicit_callback(self):
        telegram_module = types.ModuleType("telegram")

        class InlineKeyboardButton:
            def __init__(self, text, callback_data):
                self.text = text
                self.callback_data = callback_data

        class InlineKeyboardMarkup:
            def __init__(self, inline_keyboard):
                self.inline_keyboard = inline_keyboard

        telegram_module.InlineKeyboardButton = InlineKeyboardButton
        telegram_module.InlineKeyboardMarkup = InlineKeyboardMarkup

        executor = Executor(MagicMock())
        with patch.dict(sys.modules, {"telegram": telegram_module}):
            response = await executor.execute({"intent": "reminder_list", "action": "list", "params": {}}, Config.ALLOWED_USER_ID)

        self.assertIsInstance(response, dict)
        keyboard = response["reply_markup"].inline_keyboard
        callbacks = [button.callback_data for row in keyboard for button in row]
        self.assertIn("reminder_delete_menu", callbacks)
        self.assertNotIn("cancelar lembrete", callbacks)

    async def test_automation_list_uses_loaded_engine_rules(self):
        app = MagicMock()
        app.bot_data = {
            "automation": MagicMock(rules=[
                {"id": "r1", "name": "Regra Real", "enabled": True, "trigger": {"type": "time", "time": "08:00"}},
            ])
        }
        executor = Executor(app)

        response = await executor.execute({"intent": "automation_list", "action": "list", "params": {}}, Config.ALLOWED_USER_ID)

        self.assertIn("Regra Real", response)
        self.assertNotIn("Modo Noturno (22h - 08h)", response)

    async def test_automation_create_does_not_fake_registration(self):
        executor = Executor(MagicMock())
        response = await executor.execute({"intent": "automation_create", "action": "create", "params": {}}, Config.ALLOWED_USER_ID)

        self.assertIn("não consigo criar", response)
        self.assertNotIn("registrada", response.lower())

    async def test_persistence_event_log(self):
        event = Event(type="test.event", source="test", payload={"foo": "bar"})
        Persistence.log_event(event)

        events = Persistence.get_recent_events(10)
        found = any(e["id"] == event.id for e in events)
        self.assertTrue(found)

    async def test_reminders_flow_conversation(self):
        chat_id = 999
        # 1. Start Flow
        params = {"action_type": "hydration", "minutes": 60, "repeat": True, "text": "Drink water"}
        response = RemindersFlow.start_flow(chat_id, params)
        self.assertIn("meta diária", response)

        # Verify context saved
        ctx = ContextEngine.get_context(chat_id)
        self.assertIsNotNone(ctx.get("flow"))
        self.assertEqual(ctx["flow"]["step"], "ask_meta")

        # 2. Provide Meta (with normalization)
        # Note: In real flow, router would detect flow and call handle_response.
        # Here we call handle_response directly.
        response = RemindersFlow.handle_response(chat_id, "6 litros", ctx)
        # The personality message is "Beleza. Meta definida. E qual o tamanho do seu copo (em ml)?"
        self.assertIn("Meta definida", response)
        self.assertIn("tamanho do seu copo", response)

        # Verify context updated
        ctx = ContextEngine.get_context(chat_id)
        self.assertEqual(ctx["flow"]["step"], "ask_cup")
        self.assertEqual(ctx["flow"]["data"]["meta_ml"], 6000)

        # 3. Provide Cup
        response = RemindersFlow.handle_response(chat_id, "300ml", ctx)
        # Personality string: "Show! Lembrete de hidratação salvo."
        self.assertIn("Hidratação configurada", response)

        # Verify flow cleared
        ctx = ContextEngine.get_context(chat_id)
        self.assertIsNone(ctx.get("flow"))

if __name__ == '__main__':
    unittest.main()
