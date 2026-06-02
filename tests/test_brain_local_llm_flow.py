from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.core.brain import Brain
from jarvis.core.llm_fallback import LOCAL_LLM_TIMEOUT_MESSAGE


@pytest.mark.asyncio
async def test_brain_uses_local_llm_for_open_question():
    brain = Brain()
    brain.local_brain.process = AsyncMock(return_value=None)
    brain.local_llm.generate_chat_response = MagicMock(return_value="USB é um padrão de conexão.")

    result = await brain.process_intent("o que e usb")

    assert result["source"] == "local_llm"
    assert result["params"]["response"] == "USB é um padrão de conexão."


@pytest.mark.asyncio
async def test_brain_does_not_invent_realtime_data_without_external_access():
    brain = Brain()
    brain.local_brain.process = AsyncMock(return_value=None)
    brain.local_llm.generate_chat_response = MagicMock(return_value="Tabela inventada")

    result = await brain.process_intent("tabela do brasileirao")

    assert result["source"] == "brasileirao_config"
    assert "fonte local gratuita" in result["params"]["response"].lower()
    brain.local_llm.generate_chat_response.assert_not_called()


@pytest.mark.asyncio
async def test_brain_answers_mothers_day_with_local_calendar_rule():
    brain = Brain()
    brain.local_brain.process = AsyncMock(return_value=None)

    result = await brain.process_intent("quando e o dia das maes")

    assert result["source"] == "local_calendar"
    assert "segundo domingo de maio" in result["params"]["response"]


@pytest.mark.asyncio
async def test_brain_sends_collected_current_context_to_local_llm():
    brain = Brain()
    brain.local_brain.process = AsyncMock(return_value=None)
    brain.current_info.collect = MagicMock(return_value=MagicMock(
        ok=True,
        answer="",
        context="Cotação USD-BRL: Compra 5.10",
        source="awesomeapi",
        error="",
    ))
    brain.local_llm.generate_response_with_context = MagicMock(return_value="O dólar está em torno de R$ 5,10.")

    result = await brain.process_intent("cotacao do dolar agora")

    assert result["source"] == "local_llm_awesomeapi"
    brain.local_llm.generate_response_with_context.assert_called_once_with(
        "cotacao do dolar agora",
        "Cotação USD-BRL: Compra 5.10",
    )


@pytest.mark.asyncio
async def test_brain_returns_clear_fallback_when_local_llm_fails():
    brain = Brain()
    brain.local_brain.process = AsyncMock(return_value=None)
    brain.local_llm.generate_chat_response = MagicMock(return_value=None)

    result = await brain.process_intent("explique um assunto aleatorio")

    assert result["params"]["response"] == LOCAL_LLM_TIMEOUT_MESSAGE
