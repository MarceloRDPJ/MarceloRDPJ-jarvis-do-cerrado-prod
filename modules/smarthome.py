import tinytuya
import asyncio
import logging

from config import Config
from core.utils import retry_with_backoff

logger = logging.getLogger(__name__)


class SmartHomeModule:
    """
    Módulo de automação residencial (Tuya).
    Responsável apenas por executar ações em dispositivos.
    """

    # ==========================================================
    # 🔍 CONTRATOS USADOS PELO EXECUTOR
    # ==========================================================

    @classmethod
    def has_device(cls, device_name: str) -> bool:
        """
        Verifica se o dispositivo existe no cadastro Tuya.
        """
        if not device_name:
            return False

        for name, data in Config.TUYA_DEVICES.items():
            if device_name.lower() in name.lower():
                return bool(data.get("id") and data.get("key") and data.get("ip"))
        return False

    @classmethod
    async def get_device_status(cls, device_name: str) -> str:
        """
        Consulta status básico do dispositivo.
        """
        if not cls.has_device(device_name):
            return f"❌ A {device_name} não tá cadastrada ainda, uai."

        try:
            return await cls.control_device(device_name, "status")
        except Exception as e:
            logger.error(f"Erro ao consultar status {device_name}: {e}")
            return f"⚠️ Não consegui consultar o status da {device_name}."

    # ==========================================================
    # ⚙️ CONTROLE PRINCIPAL (ASYNC)
    # ==========================================================

    @staticmethod
    @retry_with_backoff(retries=3)
    async def control_device(device_name, action, value=None):
        """
        Wrapper assíncrono para controle de dispositivos Tuya.
        """
        return await asyncio.to_thread(
            SmartHomeModule._control_device_sync,
            device_name,
            action,
            value
        )

    # ==========================================================
    # 🔧 CONTROLE SINCRONO REAL (TINYTUYA)
    # ==========================================================

    @staticmethod
    def _control_device_sync(device_name, action, value=None):
        target = None

        # Busca dispositivo no Config
        for name, data in Config.TUYA_DEVICES.items():
            if device_name and device_name.lower() in name.lower():
                target = data
                break

        if not target:
            return f"❌ Dispositivo '{device_name}' não achei aqui não, uai."

        try:
            device = tinytuya.OutletDevice(
                dev_id=target["id"],
                address=target["ip"],
                local_key=target["key"],
                version=target.get("ver", "3.3")
            )
        except Exception as e:
            logger.error(f"Erro ao inicializar Tuya {device_name}: {e}")
            return f"❌ Falha ao conectar na {device_name}."

        # ======================================================
        # 📊 STATUS
        # ======================================================
        if action == "status":
            status = device.status()
            return f"📊 Status da {device_name}: {status}"

        # ======================================================
        # 💡 CONTROLES BÁSICOS
        # ======================================================
        if action == "turn_on":
            device.turn_on()
            return f"💡 {device_name} ligada. Botei pra torar."

        if action == "turn_off":
            device.turn_off()
            return f"🌑 {device_name} desligada. Apagou tudo."

        # ======================================================
        # 🔧 DP AVANÇADO
        # ======================================================
        if action == "set_dp":
            if isinstance(value, dict) and "dp" in value and "val" in value:
                device.set_value(index=value["dp"], value=value["val"])
                return f"🔧 DP {value['dp']} setado pra {value['val']}."
            return "❌ Valor inválido pra set_dp."

        # ======================================================
        # 🔓 FECHADURA (CASOS ESPECIAIS)
        # ======================================================
        if action == "unlock_fingerprint":
            device.turn_on()  # padrão Tuya para destravar
            return f"🔓 Fechadura {device_name} liberada pra cadastrar digital."

        # ======================================================
        # ❓ FALLBACK
        # ======================================================
        return f"❓ Ação '{action}' não sei fazer não."
