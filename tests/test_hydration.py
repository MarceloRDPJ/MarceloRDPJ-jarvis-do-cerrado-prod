import unittest
from unittest.mock import MagicMock, patch
import json
from datetime import datetime, timezone

from jarvis.modules.hydration import HydrationModule
from jarvis.core.context import ContextEngine
from jarvis.database.persistence import Persistence

class TestHydrationModule(unittest.TestCase):

    def setUp(self):
        self.chat_id = 12345
        # Mock initial state
        self.default_state = {
            "active": True,
            "daily_goal_ml": 2500,
            "cup_size_ml": 250,
            "interval_minutes": 60,
            "consumed_today_ml": 0,
            "last_drink_at": None,
            "last_reminder_at": None,
            "quiet_hours": {"start": "22:00", "end": "08:00"},
            "last_reset_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        }

    @patch("jarvis.modules.hydration.Persistence")
    @patch("jarvis.modules.hydration.ContextEngine")
    def test_activate_flow(self, mock_context, mock_persistence):
        # Test activation start
        response = HydrationModule.activate_flow(self.chat_id)

        # Verify context set
        mock_context.save_context.assert_called()
        args = mock_context.save_context.call_args[0]
        self.assertEqual(args[0], self.chat_id)
        self.assertEqual(args[1]['flow']['type'], 'hydration_setup')
        self.assertIn("meta diária", response)

    @patch("jarvis.modules.hydration.Persistence")
    @patch("jarvis.modules.hydration.ContextEngine")
    def test_handle_flow_steps(self, mock_context, mock_persistence):
        # 1. Goal Step
        ctx = {"flow": {"step": "ask_goal", "data": {}}}
        response = HydrationModule.handle_flow(self.chat_id, "3000", ctx)
        self.assertIn("tamanho do seu copo", response)
        # Verify next step saved
        mock_context.save_context.assert_called()
        saved_flow = mock_context.save_context.call_args[0][1]['flow']
        self.assertEqual(saved_flow['step'], 'ask_cup')
        self.assertEqual(saved_flow['data']['daily_goal_ml'], 3000)

        # 2. Cup Step
        ctx = {"flow": {"step": "ask_cup", "data": {"daily_goal_ml": 3000}}}
        response = HydrationModule.handle_flow(self.chat_id, "250", ctx)
        self.assertIn("quanto tempo", response)
        saved_flow = mock_context.save_context.call_args[0][1]['flow']
        self.assertEqual(saved_flow['step'], 'ask_interval')
        self.assertEqual(saved_flow['data']['cup_size_ml'], 250)

        # 3. Interval Step (Finish)
        # Mock loading state (Persistence.get_state) to update it
        mock_persistence.get_state.return_value = self.default_state.copy()
        # Mock tasks check (empty list -> create new)
        mock_persistence.get_tasks_by_action.return_value = []

        ctx = {"flow": {"step": "ask_interval", "data": {"daily_goal_ml": 3000, "cup_size_ml": 250}}}
        response = HydrationModule.handle_flow(self.chat_id, "60", ctx)
        self.assertIn("Hidratação ativada", response)

        # Verify state saved
        mock_persistence.set_state.assert_called()
        key, state = mock_persistence.set_state.call_args[0]
        self.assertEqual(state['interval_minutes'], 60)
        self.assertEqual(state['daily_goal_ml'], 3000)

        # Verify trigger task created
        mock_persistence.add_task.assert_called()

    @patch("jarvis.modules.hydration.Persistence")
    def test_log_intake_explicit(self, mock_persistence):
        # Setup state
        state = self.default_state.copy()
        mock_persistence.get_state.return_value = state

        # Test "bebi" (explicit)
        response = HydrationModule.log_intake(self.chat_id, manual=True, explicit=True)

        # Verify state update
        self.assertEqual(state['consumed_today_ml'], 250)
        mock_persistence.set_state.assert_called()
        self.assertIn("250", response)

    @patch("jarvis.modules.hydration.Persistence")
    def test_log_intake_implicit_fail(self, mock_persistence):
        # Setup state (no reminder sent)
        state = self.default_state.copy()
        state['last_reminder_at'] = None
        mock_persistence.get_state.return_value = state

        # Test "ok" (implicit)
        response = HydrationModule.log_intake(self.chat_id, manual=True, explicit=False)

        # Verify failure
        self.assertIn("Ok o que?", response)
        # Verify NOT saved (consumed not updated)
        self.assertEqual(state['consumed_today_ml'], 0)

    @patch("jarvis.modules.hydration.Persistence")
    def test_control_pause(self, mock_persistence):
        # Setup
        state = self.default_state.copy()
        state['active'] = True
        mock_persistence.get_state.return_value = state

        # Test
        response = HydrationModule.control_hydration(self.chat_id, "pausar")

        # Verify
        self.assertFalse(state['active'])
        mock_persistence.set_state.assert_called()
        self.assertIn("pausada", response)

    @patch("jarvis.modules.hydration.Persistence")
    def test_update_config(self, mock_persistence):
        # Setup
        state = self.default_state.copy()
        mock_persistence.get_state.return_value = state

        # Test "meta 5000"
        params = {"text": "meta 5000", "value": 5000}
        response = HydrationModule.update_config(self.chat_id, params)

        # Verify
        self.assertEqual(state['daily_goal_ml'], 5000)
        mock_persistence.set_state.assert_called()
        self.assertIn("5000ml", response)

    def test_today_stats_use_hydration_log_without_task(self):
        Persistence.log_hydration_intake(
            chat_id=self.chat_id,
            amount_ml=300,
            goal_ml=2500,
            consumed_so_far_ml=300,
            manual=True,
        )

        self.assertEqual(Persistence.get_hydration_count_today(self.chat_id), 1)
        self.assertEqual(Persistence.get_hydration_volume_today(self.chat_id), 300)

if __name__ == "__main__":
    unittest.main()
