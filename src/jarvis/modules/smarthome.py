import logging

logger = logging.getLogger("modules.smarthome")

class SmartHomeModule:
    """
    Stub temporário.
    Nenhuma integração de casa inteligente ativa.
    """

    @staticmethod
    async def execute(*args, **kwargs):
        return {
            "status": "disabled",
            "message": "SmartHome desativado temporariamente"
        }
