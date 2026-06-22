import pytest
from unittest.mock import AsyncMock, patch
from jarvis.modules.adguard import AdGuardClient

@pytest.mark.asyncio
async def test_block_client_success():
    """Testa bloqueio bem-sucedido de cliente"""
    with patch('aiohttp.ClientSession.post') as mock_post:
        # Configura o mock do contexto assíncrono (__aenter__ e __aexit__)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_post.return_value.__aenter__.return_value = mock_response

        result = await AdGuardClient.block_client("192.168.0.100")

        assert result["success"] == True
        assert "regra" in result["message"].lower()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["url"] == "||192.168.0.100^"

@pytest.mark.asyncio
async def test_block_client_failure():
    """Testa falha ao bloquear cliente"""
    with patch('aiohttp.ClientSession.post') as mock_post:
        # Configura o mock para lançar exceção
        mock_post.side_effect = Exception("Connection refused")

        result = await AdGuardClient.block_client("192.168.0.100")

        assert result["success"] == False
        assert "erro" in result["message"].lower()

@pytest.mark.asyncio
async def test_block_client_rejects_domain_as_ip():
    result = await AdGuardClient.block_client("youtube.com")

    assert result["success"] == False
    assert "ip inválido" in result["message"].lower()

@pytest.mark.asyncio
async def test_block_domain_uses_domain_rule():
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_post.return_value.__aenter__.return_value = mock_response

        result = await AdGuardClient.block_domain("https://youtube.com/watch?v=1")

        assert result["success"] == True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["url"] == "||youtube.com^"
