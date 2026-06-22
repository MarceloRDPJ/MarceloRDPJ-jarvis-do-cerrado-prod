from types import SimpleNamespace

import pytest

from jarvis.api.integration_engine import IntegrationEngine


def test_workflow_validation_rejects_dashboard_value_only_step():
    engine = IntegrationEngine(SimpleNamespace())

    errors = engine.validate_config({
        "name": "Fluxo quebrado",
        "type": "workflow",
        "config": {"steps": [{"type": "schedule", "config": {"value": "22:00"}}]},
    })

    assert errors
    assert "schedule precisa" in errors[0]


def test_chatbot_validation_rejects_legacy_steps_shape():
    engine = IntegrationEngine(SimpleNamespace())

    errors = engine.validate_config({
        "name": "Chat quebrado",
        "type": "chatbot",
        "config": {"trigger": "oi", "message": "ola", "steps": []},
    })

    assert errors == ["chatbot precisa de config.flows com ao menos um fluxo"]


def test_register_integration_rejects_invalid_config():
    engine = IntegrationEngine(SimpleNamespace())

    with pytest.raises(ValueError):
        engine.register_integration({
            "name": "Fluxo inválido",
            "type": "workflow",
            "config": {"steps": [{"type": "notification", "config": {}}]},
        })


@pytest.mark.asyncio
async def test_integration_test_endpoint_returns_invalid(monkeypatch):
    from jarvis.api import app as api_app

    engine = IntegrationEngine(SimpleNamespace())
    monkeypatch.setattr(api_app, "get_service", lambda name: engine)

    class Request:
        async def json(self):
            return {
                "name": "Chat quebrado",
                "type": "chatbot",
                "config": {"trigger": "oi", "message": "ola", "steps": []},
            }

    request = Request()

    result = await api_app.test_integration(request)

    assert result["status"] == "invalid"
    assert result["errors"]


@pytest.mark.asyncio
async def test_integration_templates_use_valid_chatbot_schema():
    from jarvis.api.app import list_integration_templates

    data = await list_integration_templates()
    chatbot_templates = [tpl for tpl in data["templates"] if tpl["type"] == "chatbot"]

    assert chatbot_templates
    assert "flows" in chatbot_templates[0]
    assert "steps" not in chatbot_templates[0]
