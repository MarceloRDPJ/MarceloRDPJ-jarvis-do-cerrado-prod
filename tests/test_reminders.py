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

    def test_time_parser_absolute(self):
        # Test "Sábado às 14h"
        # Since "Sábado" is relative to today, we need to be careful with assertions.
        # But we can check if it returns a target_date.
        res = parse_time_command("me lembre sábado às 14h")
        self.assertIsNotNone(res["target_date"])
        self.assertIsInstance(res["target_date"], datetime)
        self.assertEqual(res["target_date"].hour, 14)
        self.assertEqual(res["target_date"].minute, 0)
        self.assertIsNotNone(res["formatted"])

    def test_time_parser_relative(self):
        res = parse_time_command("daqui a 10 minutos")
        self.assertEqual(res["minutes"], 10)
        self.assertIsNotNone(res["target_date"])
        # Should be roughly now + 10m
        diff = res["target_date"] - datetime.now()
        self.assertTrue(timedelta(minutes=9) < diff < timedelta(minutes=11))

    def test_flow_happy_path(self):
        chat_id = 1001
        # Clear context
        ContextEngine.save_context(chat_id, {"flow": None})

        # 1. Start Flow with full info
        target_date = datetime.now() + timedelta(days=1)
        params = {
            "text": "Puxar talões",
            "target_date": target_date,
            "minutes": 1440
        }

        resp = RemindersFlow.start_flow(chat_id, params)
        # Expect confirmation message
        self.assertIn("Então ficou assim", resp)
        self.assertIn("Puxar talões", resp)
        self.assertIn("Confirma?", resp)

        # Verify state
        ctx = ContextEngine.get_context(chat_id)
        self.assertEqual(ctx["flow"]["step"], "confirmation")

        # 2. Confirm
        resp = RemindersFlow.handle_response(chat_id, "sim", ctx)
        self.assertIn("Combinado", resp)
        self.assertIn("Lembrete salvo", resp)

        # Verify DB
        tasks = Persistence.get_active_tasks(chat_id)
        self.assertTrue(len(tasks) > 0)
        latest = tasks[-1]
        self.assertEqual(latest["text"], "Puxar talões")

    def test_flow_missing_time(self):
        chat_id = 1002
        ContextEngine.save_context(chat_id, {"flow": None})

        # 1. Start without time
        params = {"text": "Comprar pão"}
        resp = RemindersFlow.start_flow(chat_id, params)
        self.assertIn("Que horas", resp)

        # Verify state
        ctx = ContextEngine.get_context(chat_id)
        self.assertEqual(ctx["flow"]["step"], "awaiting_clarification")
        self.assertEqual(ctx["flow"]["missing_field"], "time")

        # 2. Provide time
        resp = RemindersFlow.handle_response(chat_id, "às 18h", ctx)
        self.assertIn("Então ficou assim", resp)
        self.assertIn("18h", resp) # check formatted string contains 18h
        self.assertIn("Confirma?", resp)

        # Verify state
        ctx = ContextEngine.get_context(chat_id)
        self.assertEqual(ctx["flow"]["step"], "confirmation")

    def test_management(self):
        chat_id = 1003
        ContextEngine.save_context(chat_id, {"flow": None})

        # Create dummy tasks
        Persistence.add_task(chat_id, "Task 1", datetime.now(), "default")
        Persistence.add_task(chat_id, "Task 2", datetime.now(), "default")

        # List
        resp = RemindersFlow.list_reminders(chat_id)
        self.assertIn("Task 1", resp)
        self.assertIn("Task 2", resp)

        # Delete
        resp = RemindersFlow.delete_reminder(chat_id, 1) # Delete 1st
        self.assertIn("Feito", resp)
        self.assertIn("apagado", resp)

        # Verify deletion
        tasks = Persistence.get_active_tasks(chat_id)
        texts = [t["text"] for t in tasks]
        self.assertNotIn("Task 1", texts)
        self.assertIn("Task 2", texts)

if __name__ == '__main__':
    unittest.main()
