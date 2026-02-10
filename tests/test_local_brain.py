from jarvis.core.brain import Brain
import pytest

@pytest.mark.asyncio
async def test_brain_local_fallback():
    brain = Brain()

    # Test local knowledge base
    result = await brain.process_intent("quem é você")
    assert result is not None
    assert result["intent"] == "chat"
    assert "Jarvis do Cerrado" in result["response"]
    assert result["source"] == "local_brain"

    # Test fuzzy matching
    result_fuzzy = await brain.process_intent("qm e vc")
    assert result_fuzzy is not None
    assert "Jarvis" in result_fuzzy["response"]

    # Test unknown command (fallback)
    result_unknown = await brain.process_intent("comando_inexistente_xyz_123")
    assert result_unknown["intent"] == "chat"
    # Fallback message might vary, but shouldn't be empty
    assert len(result_unknown["response"]) > 0
