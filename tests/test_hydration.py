import unittest
from unittest.mock import MagicMock, patch
import json
from datetime import datetime, timezone

# Mock Persistence before importing HydrationModule because it imports Persistence
# Actually, we can patch it inside the test methods or setup.

from jarvis.modules.hydration import HydrationModule
from jarvis.core.context import ContextEngine

class TestHydrationModule(unittest.TestCase):

    def setUp(self):
        self.chat_id = 12345
        self.task_id = 1
        self.ctx = {
            "flow": {
                "type": "hydration_confirm",
                "task_id": self.task_id,
                "cup_ml": 250,
                "timestamp": "2023-10-27T10:00:00+00:00"
            }
        }

    @patch("jarvis.modules.hydration.Persistence")
    @patch("jarvis.modules.hydration.ContextEngine")
    def test_handle_flow_positive(self, mock_context, mock_persistence):
        # Setup
        mock_persistence.get_hydration_volume_today.return_value = 500
        mock_persistence.get_tasks_by_action.return_value = [{"id": 1, "meta": '{"meta_ml": 2000}'}]

        # Test "sim"
        response = HydrationModule.handle_flow(self.chat_id, "sim", self.ctx)

        # Verify
        mock_context.save_context.assert_called_with(self.chat_id, {"flow": None})
        mock_persistence.log_interaction.assert_called_with(self.task_id, "confirm", "250")
        self.assertIn("500", response)

    @patch("jarvis.modules.hydration.Persistence")
    @patch("jarvis.modules.hydration.ContextEngine")
    def test_handle_flow_negative(self, mock_context, mock_persistence):
        # Test "não"
        response = HydrationModule.handle_flow(self.chat_id, "não", self.ctx)

        # Verify
        mock_context.save_context.assert_called_with(self.chat_id, {"flow": None})
        mock_persistence.log_interaction.assert_not_called()
        self.assertIn("Tranquilo", response)

    @patch("jarvis.modules.hydration.Persistence")
    def test_log_intake_manual(self, mock_persistence):
        # Setup
        mock_persistence.get_tasks_by_action.return_value = [{"id": 1, "meta": '{"meta_ml": 2000}'}]
        mock_persistence.get_hydration_volume_today.return_value = 300

        # Test
        response = HydrationModule.log_intake(self.chat_id, 300, manual=True)

        # Verify
        mock_persistence.log_interaction.assert_called_with(1, "confirm", "300")
        self.assertIn("300", response)

    @patch("jarvis.modules.hydration.Persistence")
    def test_control_pause(self, mock_persistence):
        # Setup
        mock_persistence.get_tasks_by_action.return_value = [{"id": 1, "status": "active"}]

        # Test
        response = HydrationModule.control_hydration(self.chat_id, "pausar lembrete")

        # Verify
        mock_persistence.update_task_status.assert_called_with(1, "paused")
        self.assertIn("pausei", response)

    @patch("jarvis.modules.hydration.Persistence")
    def test_control_resume(self, mock_persistence):
        # Setup
        mock_persistence.get_tasks_by_action.return_value = [] # No active tasks
        # Mock paused tasks
        mock_persistence.get_tasks_by_status.return_value = [{"id": 1, "status": "paused"}]

        # Test
        response = HydrationModule.control_hydration(self.chat_id, "retomar hidratação")

        # Verify
        mock_persistence.update_task_status.assert_called_with(1, "active")
        self.assertIn("retomada", response)

if __name__ == "__main__":
    unittest.main()
