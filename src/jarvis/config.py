import os
import yaml
import pytz
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ==================================================
    # TIMEZONE
    # ==================================================
    TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")
    TZ = pytz.timezone(TIMEZONE)

    # ==================================================
    # TUNING / MAGIC NUMBERS
    # ==================================================
    INTENT_CONFIDENCE_THRESHOLD = float(os.getenv("INTENT_CONFIDENCE_THRESHOLD", 0.88))
    SCHEDULER_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", 30))
    HYDRATION_MIN_INTERVAL_MINUTES = int(os.getenv("HYDRATION_MIN_INTERVAL_MINUTES", 10))

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


        if missing:
            raise RuntimeError(
                f"Configuração incompleta. Variáveis ausentes: {', '.join(missing)}"
            )
