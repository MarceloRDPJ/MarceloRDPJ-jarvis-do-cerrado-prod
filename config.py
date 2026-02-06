import os
import yaml
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ==================================================
    # TELEGRAM
    # ==================================================
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))

    # ==================================================
    # GEMINI (LLM)
    # ==================================================
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # ==================================================
    # NETWORK / SYSTEM
    # ==================================================
    PC_MAC = os.getenv("PC_MAC", "00:00:00:00:00:00")

    # ==================================================
    # TUYA CLOUD (OFICIAL – PRINCIPAL)
    # ==================================================
    TUYA_ACCESS_ID = os.getenv("TUYA_ACCESS_ID")
    TUYA_ACCESS_SECRET = os.getenv("TUYA_ACCESS_SECRET")
    TUYA_REGION = os.getenv("TUYA_REGION", "us")  # us = Americas

    # ==================================================
    # TUYA DEVICES (MAPEAMENTO LÓGICO)
    # NÃO É LOCAL, É IDENTIDADE DO BOT
    # ==================================================
    TUYA_DEVICES = {
        "fechadura": {
            "name": "Fechadura Principal",
            "type": "lock",
            "cloud": True,
            "device_id": os.getenv("TUYA_LOCK_ID"),  # vem da Tuya Cloud
            "brand": "COIBEU",
        },
        "luz_sala": {
            "name": "Luz da Sala",
            "type": "light",
            "cloud": True,
            "device_id": os.getenv("TUYA_LIGHT_ID"),
        },
    }

    # ==================================================
    # CONFIG.YAML (COMPORTAMENTO)
    # ==================================================
    YAML_CONFIG = {}
    try:
        with open(os.path.join(os.path.dirname(__file__), "config.yaml"), "r") as f:
            YAML_CONFIG = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[WARN] Não foi possível carregar config.yaml: {e}")

    @staticmethod
    def get(path, default=None):
        """
        Get config value by dot notation
        Ex: Config.get("system.retry_attempts")
        """
        keys = path.split(".")
        val = Config.YAML_CONFIG
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    # ==================================================
    # VALIDATIONS (OPCIONAL MAS PROFISSIONAL)
    # ==================================================
    @staticmethod
    def validate():
        missing = []

        if not Config.TELEGRAM_TOKEN:
            missing.append("TELEGRAM_TOKEN")

        if not Config.ALLOWED_USER_ID:
            missing.append("ALLOWED_USER_ID")

        if not Config.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")

        if not Config.TUYA_ACCESS_ID:
            missing.append("TUYA_ACCESS_ID")

        if not Config.TUYA_ACCESS_SECRET:
            missing.append("TUYA_ACCESS_SECRET")

        if missing:
            raise RuntimeError(
                f"Configuração incompleta. Variáveis ausentes: {', '.join(missing)}"
            )
