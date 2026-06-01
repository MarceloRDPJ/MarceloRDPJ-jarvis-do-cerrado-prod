import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from jarvis.core.executor import Executor
from jarvis.core.context import ContextEngine
from jarvis.core.brain import Brain
from jarvis.core.llm_fallback import LLMFallbackEngine
from jarvis.modules.hydration import HydrationModule

@pytest.mark.asyncio
async def test_executor_routes_hydration_setup():
    # Setup
    mock_app = MagicMock()
    executor = Executor(mock_app)
    chat_id = 12345

    # Mock Allowed User
    from jarvis.config import Config
    Config.ALLOWED_USER_ID = chat_id

    # Mock Context
    with patch.object(ContextEngine, 'get_context', return_value={
        "flow": {
            "type": "hydration_setup",
            "step": "ask_goal",
            "data": {}
        }
    }):
        # Mock HydrationModule
        with patch.object(HydrationModule, 'handle_flow', return_value="Setup Handled") as mock_handle:

            # Execute
            intent_data = {
                "intent": "flow_input",
                "params": {"text": "5000"}
            }
            response = await executor.execute(intent_data, chat_id)

            # Verify
            mock_handle.assert_called_once()
            assert response == "Setup Handled"

@pytest.mark.asyncio
async def test_brain_llm_fallback():
    # Setup
    brain = Brain()

    # Mock LocalBrain to return None (miss)
    brain.local_brain.process = AsyncMock(return_value=None)

    # Mock Local LLM
    brain.local_llm = MagicMock()
    brain.local_llm.generate_chat_response.return_value = "Local LLM Response"

    # Execute
    result = await brain.process_intent("some random text")

    # Verify
    assert result["intent"] == "chat"
    assert result["response"] == "Local LLM Response"
    assert result["source"] == "local_llm"

def test_llm_fallback_engine_chat():
    engine = LLMFallbackEngine()
    engine.backend = "llamacpp"

    # Mock requests.post
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"content": "  Hello World  "}
        mock_post.return_value = mock_response

        response = engine.generate_chat_response("Hi")

        assert response == "Hello World"
        assert mock_post.called

def test_llm_fallback_engine_interpret():
    engine = LLMFallbackEngine()
    engine.backend = "llamacpp"

    # Mock requests.post
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"content": '{"intent": "chat"}'}
        mock_post.return_value = mock_response

        result = engine.interpret("Hi")

        assert result == {"intent": "chat"}
        assert mock_post.called

def test_llm_fallback_engine_cli_chat():
    engine = LLMFallbackEngine()
    engine.backend = "llamacpp_cli"
    engine.cli_path = "/opt/bot/llama.cpp/build/bin/llama-cli"
    engine.model_path = "/opt/bot/models/model.gguf"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""
build      : test
model      : model.gguf
> prompt
  Oi, Marcelo.
[ Prompt: 10 t/s | Generation: 8 t/s ]
""",
            stderr="",
        )

        response = engine.generate_chat_response("Hi")

        assert response == "Oi, Marcelo."
        assert mock_run.called
