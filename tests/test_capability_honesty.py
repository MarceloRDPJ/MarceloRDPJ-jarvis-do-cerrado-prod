import pytest

from jarvis.modules.smarthome import SmartHomeModule


@pytest.mark.asyncio
async def test_smarthome_direct_execute_reports_not_configured():
    result = await SmartHomeModule.execute("ligar luz")

    assert result["status"] == "not_configured"
    assert "não configurado" in result["message"]


@pytest.mark.asyncio
async def test_smarthome_unknown_device_reports_not_configured():
    result = await SmartHomeModule.control_device("luz_sala", "on")

    assert result["status"] == "not_configured"


@pytest.mark.asyncio
async def test_fan_status_exposes_simulated_hardware(monkeypatch):
    from types import SimpleNamespace
    from jarvis.api import app as api_app

    monkeypatch.setattr(
        api_app,
        "get_service",
        lambda name: SimpleNamespace(
            fan=None,
            manual_override=False,
            threshold_on=60,
            threshold_off=50,
            pin=18,
        ),
    )

    response = await api_app.get_fan_status()
    assert response.body
    assert b'"available":false' in response.body
    assert b'"hardware_status":"simulated"' in response.body
