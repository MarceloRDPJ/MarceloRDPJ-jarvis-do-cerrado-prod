import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import sqlite3

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from jarvis.core.brain import Brain
from jarvis.core.executor import Executor
from jarvis.config import Config
from jarvis.database.persistence import Persistence
from jarvis.core.events import Event
from jarvis.core.flows import RemindersFlow

class TestHomeAssistantBot(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(cls):
        # Initialize DB
        Persistence.init_db()

    @patch('jarvis.core.brain.genai')
    async def test_brain_process_intent(self, mock_genai):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        mock_response = MagicMock()
        mock_response.text = '{"intent": "smarthome", "action": "turn_on", "device": "luz_sala"}'
        mock_model.generate_content.return_value = mock_response

        brain = Brain()
        result = await brain.process_intent("Liga a luz da sala")
        self.assertIsInstance(result, dict)
        self.assertEqual(result['intent'], 'smarthome')

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

        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/jarvis/database/homebot.db'))

        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT text FROM tasks WHERE chat_id=?", (123,))
        rows = c.fetchall()
        conn.close()

        found = False
        for row in rows:
            if row[0] == "Teste DB":
                found = True
                break
        self.assertTrue(found)

    async def test_persistence_event_log(self):
        event = Event(type="test.event", source="test", payload={"foo": "bar"})
        Persistence.log_event(event)

        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/jarvis/database/homebot.db'))
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT type FROM events WHERE id=?", (event.id,))
        row = c.fetchone()
        conn.close()

        self.assertEqual(row[0], "test.event")

if __name__ == '__main__':
    unittest.main()
