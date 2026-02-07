import unittest
import sys
import os
import sqlite3
from datetime import datetime, timedelta

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from jarvis.core.flows import RemindersFlow
from jarvis.core.context import ContextEngine
from jarvis.database.persistence import Persistence
from jarvis.nlp.time_parser import parse_time_command
from jarvis.nlp.intent_engine import detect_intent

class TestReminders(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Persistence.init_db()

    def setUp(self):
        # Clean tasks table
        conn = sqlite3.connect(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/jarvis/database/homebot.db')))
        c = conn.cursor()
        c.execute("DELETE FROM tasks")
        conn.commit()
        conn.close()

    def test_text_cleaning(self):
        text = "me lembre de puxar os taloes amanha as 12h"
        result = detect_intent(text)
        clean_text = result["params"]["text"]

        # Check if time words are gone
        self.assertNotIn("amanha", clean_text.lower())
        self.assertNotIn("12h", clean_text.lower())
        self.assertIn("puxar os taloes", clean_text.lower())
        self.assertIsNotNone(result["params"]["target_date"])

    def test_time_parser_absolute(self):
        res = parse_time_command("me lembre sábado às 14h")
        self.assertIsNotNone(res["target_date"])
        self.assertIsInstance(res["target_date"], datetime)
        self.assertEqual(res["target_date"].hour, 14)

    def test_time_parser_relative(self):
        res = parse_time_command("daqui a 10 minutos")
        self.assertEqual(res["minutes"], 10)
        self.assertIsNotNone(res["target_date"])

    def test_flow_happy_path(self):
        chat_id = 1001
        ContextEngine.save_context(chat_id, {"flow": None})

        target_date = datetime.now() + timedelta(days=1)
        params = {
            "text": "Puxar talões",
            "target_date": target_date,
            "minutes": 1440
        }

        resp = RemindersFlow.start_flow(chat_id, params)
        self.assertIn("vê se tá certo", resp)
        self.assertIn("Puxar talões", resp)

        ctx = ContextEngine.get_context(chat_id)
        self.assertEqual(ctx["flow"]["step"], "confirmation")

        resp = RemindersFlow.handle_response(chat_id, "sim", ctx)
        self.assertIn("Combinado", resp)

        tasks = Persistence.get_active_tasks(chat_id)
        self.assertTrue(len(tasks) > 0)
        latest = tasks[-1]
        self.assertEqual(latest["text"], "Puxar talões")

    def test_flow_missing_time(self):
        chat_id = 1002
        ContextEngine.save_context(chat_id, {"flow": None})

        params = {"text": "Comprar pão"}
        resp = RemindersFlow.start_flow(chat_id, params)
        self.assertIn("Que horas", resp)

        ctx = ContextEngine.get_context(chat_id)
        self.assertEqual(ctx["flow"]["step"], "awaiting_clarification")

        resp = RemindersFlow.handle_response(chat_id, "às 18h", ctx)
        self.assertIn("vê se tá certo", resp)
        self.assertIn("18h", resp)

    def test_management(self):
        chat_id = 1003
        ContextEngine.save_context(chat_id, {"flow": None})

        Persistence.add_task(chat_id, "Task 1", datetime.now(), "default")
        Persistence.add_task(chat_id, "Task 2", datetime.now(), "default")

        resp = RemindersFlow.list_reminders(chat_id)
        self.assertIn("Task 1", resp)
        self.assertIn("Task 2", resp)

        resp = RemindersFlow.delete_reminder(chat_id, 1)
        self.assertIn("Pronto", resp)
        self.assertIn("Apaguei", resp)

        tasks = Persistence.get_active_tasks(chat_id)
        texts = [t["text"] for t in tasks]
        self.assertNotIn("Task 1", texts)
        self.assertIn("Task 2", texts)

    def test_update_reminder(self):
        chat_id = 1004
        Persistence.add_task(chat_id, "Old Task", datetime.now(), "default")

        resp = RemindersFlow.update_reminder(chat_id, 1, "New Text")
        self.assertIn("Lembrete atualizado", resp)

        tasks = Persistence.get_active_tasks(chat_id)
        self.assertEqual(tasks[0]["text"], "New Text")

        resp = RemindersFlow.update_reminder(chat_id, 1, "para amanhã às 18h")
        self.assertIn("Lembrete atualizado", resp)

        tasks = Persistence.get_active_tasks(chat_id)
        new_run = datetime.fromisoformat(tasks[0]["next_run"])
        self.assertEqual(new_run.hour, 18)

if __name__ == '__main__':
    unittest.main()
