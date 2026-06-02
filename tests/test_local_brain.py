import unittest
from jarvis.core.brain import Brain
from jarvis.nlp.local_brain import LocalBrain
import asyncio

class TestBrainLocalFallback(unittest.IsolatedAsyncioTestCase):
    async def test_brain_local_fallback(self):
        brain = Brain()

        # Test local knowledge base
        result = await brain.process_intent("quem é você")
        self.assertIsNotNone(result)
        self.assertEqual(result["intent"], "chat")
        self.assertIn("Jarvis do Cerrado", result["params"]["response"])
        self.assertEqual(result["source"], "local_brain")

        # Test fuzzy matching (unaccented)
        result_fuzzy = await brain.process_intent("quem e voce")
        self.assertIsNotNone(result_fuzzy)
        self.assertIn("Jarvis", result_fuzzy["params"]["response"])

        # Test unknown command (fallback)
        result_unknown = await brain.process_intent("comando_inexistente_xyz_123")
        self.assertEqual(result_unknown["intent"], "chat")
        # Should be fallback
        self.assertNotIn("Jarvis do Cerrado", result_unknown["params"]["response"])

    async def test_short_incomplete_question_does_not_fuzzy_match_ip(self):
        local_brain = LocalBrain()
        result = await local_brain.process("o que e")

        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
