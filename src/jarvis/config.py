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
    raw_id = os.getenv("ALLOWED_USER_ID", "0")
    ALLOWED_USER_ID = int(raw_id) if raw_id.strip() else 0

    # ==================================================
    # LOCAL AI (FREE FALLBACK - LLAMA.CPP)
    # ==================================================
    LOCAL_LLM_BACKEND = os.getenv("LOCAL_LLM_BACKEND", "llamacpp_cli").strip().lower()
    LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:8081/completion")
    LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "gemma-3-270m-it")
    LOCAL_LLM_CLI_PATH = os.getenv("LOCAL_LLM_CLI_PATH", "/opt/bot/llama.cpp/build/bin/llama-cli")
    LOCAL_LLM_MODEL_PATH = os.getenv("LOCAL_LLM_MODEL_PATH", "")
    LOCAL_LLM_CONTEXT_TOKENS = int(os.getenv("LOCAL_LLM_CONTEXT_TOKENS", 256))
    LOCAL_LLM_THREADS = int(os.getenv("LOCAL_LLM_THREADS", 2))
    LOCAL_LLM_TIMEOUT_SECONDS = int(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", 8))
    LOCAL_LLM_MAX_TOKENS = int(os.getenv("LOCAL_LLM_MAX_TOKENS", 96))

    # ==================================================
    # NETWORK / SYSTEM
    # ==================================================
    PC_MAC = os.getenv("PC_MAC", "")
    FAN_GPIO_PIN = int(os.getenv("FAN_GPIO_PIN", 14))
    FAN_TEMP_ON = float(os.getenv("FAN_TEMP_ON", 60.0))
    FAN_TEMP_OFF = float(os.getenv("FAN_TEMP_OFF", 50.0))

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

        if not Config.PC_MAC:
            missing.append("PC_MAC (necessário para Wake-on-LAN)")

        if missing:
            raise RuntimeError(
                f"Configuração incompleta. Variáveis ausentes: {', '.join(missing)}"
            )
