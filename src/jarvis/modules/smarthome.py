import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("modules.smarthome")

# =============================================================================
# PROVIDER INTERFACE & NOT-CONFIGURED PROVIDERS
# =============================================================================

class BaseProvider:
    """Interface base para provedores de Smart Home"""
    @classmethod
    async def execute(cls, device: Dict[str, Any], action: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("Provider deve implementar execute()")

class TuyaProvider(BaseProvider):
    """Integração futura com Tuya (Local ou Cloud)"""
    @classmethod
    async def execute(cls, device: Dict[str, Any], action: str, **kwargs) -> Dict[str, Any]:
        return {"status": "not_configured", "message": "Tuya Provider não configurado."}

class TasmotaProvider(BaseProvider):
    """Integração via MQTT/HTTP para dispositivos Tasmota"""
    @classmethod
    async def execute(cls, device: Dict[str, Any], action: str, **kwargs) -> Dict[str, Any]:
        return {"status": "not_configured", "message": "Tasmota Provider não configurado."}

class ShellyProvider(BaseProvider):
    """Integração via HTTP API para dispositivos Shelly"""
    @classmethod
    async def execute(cls, device: Dict[str, Any], action: str, **kwargs) -> Dict[str, Any]:
        return {"status": "not_configured", "message": "Shelly Provider não configurado."}

class BroadlinkProvider(BaseProvider):
    """Integração via RF/IR para Broadlink RM"""
    @classmethod
    async def execute(cls, device: Dict[str, Any], action: str, **kwargs) -> Dict[str, Any]:
        return {"status": "not_configured", "message": "Broadlink Provider não configurado."}

# =============================================================================
# MODULE CORE
# =============================================================================

class SmartHomeModule:
    """
    Módulo central de Smart Home.
    Abstrai a comunicação com diferentes provedores (Tuya, Tasmota, etc).
    """

    PROVIDERS = {
        'tuya': TuyaProvider,
        'tasmota': TasmotaProvider,
        'shelly': ShellyProvider,
        'broadlink': BroadlinkProvider
    }

    # Registro vazio por padrão: sem dispositivo real configurado, sem simulação.
    DEVICE_REGISTRY = {}

    @classmethod
    async def control_device(cls, device_name: str, action: str, **kwargs) -> Dict[str, Any]:
        """
        Controla um dispositivo pelo nome (alias).
        Ex: control_device("luz_sala", "on")
        """
        device = cls.DEVICE_REGISTRY.get(device_name)

        if not device:
            return {
                "status": "not_configured",
                "message": f"Dispositivo '{device_name}' não encontrado no registro."
            }

        provider_key = device.get("provider")
        provider = cls.PROVIDERS.get(provider_key)

        if not provider:
            return {
                "status": "error",
                "message": f"Provider '{provider_key}' não suportado para '{device_name}'."
            }

        try:
            logger.info(f"Executando {action} em {device_name} via {provider_key}")
            return await provider.execute(device, action, **kwargs)
        except Exception as e:
            logger.error(f"Erro ao controlar {device_name}: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def execute(text: str, **kwargs) -> Dict[str, Any]:
        """
        Legacy handler para compatibilidade se necessário,
        ou para processar intents genéricas de smarthome.
        """
        return {
            "status": "not_configured",
            "message": "Smart home não configurado. Cadastre dispositivos reais antes de executar comandos."
        }
