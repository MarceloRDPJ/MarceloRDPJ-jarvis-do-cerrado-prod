import psutil
import subprocess
import asyncio
import time
from datetime import timedelta
from typing import Dict, Any

START_TIME = time.time()


class SystemModule:
    """
    SystemModule

    RESPONSABILIDADES:
    - Coleta RAW
    - Status HUMANO
    """

    # ==================================================
    # RAW SYSTEM DATA (PASSO 5)
    # ==================================================
    @staticmethod
    async def get_raw_status() -> Dict[str, Any]:
        return await asyncio.to_thread(SystemModule._get_raw_status_sync)

    @staticmethod
    def _get_raw_status_sync() -> Dict[str, Any]:
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        temp = None
        try:
            # Tenta ler arquivo do sistema primeiro (mais rápido e padrão Linux)
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                temp = int(f.read()) / 1000
        except Exception:
            # Fallback para vcgencmd (específico Raspberry Pi antigo)
            try:
                out = subprocess.check_output(
                    "vcgencmd measure_temp",
                    shell=True,
                    stderr=subprocess.DEVNULL
                ).decode()
                temp = float(out.replace("temp=", "").replace("'C", "").strip())
            except Exception:
                temp = None

        return {
            "timestamp": time.time(),
            "uptime_seconds": int(time.time() - START_TIME),
            "cpu_percent": cpu_percent,
            "memory": {
                "percent": mem.percent,
                "used": mem.used,
                "total": mem.total,
            },
            "disk": {
                "percent": disk.percent,
                "used": disk.used,
                "total": disk.total,
            },
            "temperature_c": temp,
        }

    # ==================================================
    # HUMANO — STATUS PARA CHAT
    # ==================================================
    @staticmethod
    async def get_status() -> str:
        raw = await SystemModule.get_raw_status()

        temp = (
            f"{raw['temperature_c']}°C"
            if raw["temperature_c"] is not None
            else "N/A"
        )

        uptime = str(timedelta(seconds=raw["uptime_seconds"]))

        return (
            "🖥️ *Status do Sistema*\n"
            f"- CPU: {raw['cpu_percent']}%\n"
            f"- RAM: {raw['memory']['percent']}%\n"
            f"- Disco: {raw['disk']['percent']}%\n"
            f"- Temp: {temp}\n"
            f"- Uptime: {uptime}"
        )

    # ==================================================
    # HEALTHCHECK
    # ==================================================
    @staticmethod
    async def get_health() -> str:
        uptime = str(timedelta(seconds=int(time.time() - START_TIME)))
        return f"✅ Healthcheck OK\nUptime: {uptime}"

    # ==================================================
    # DOCKER (HUMANO)
    # ==================================================
    @staticmethod
    async def list_docker() -> str:
        return await asyncio.to_thread(SystemModule._list_docker_sync)

    @staticmethod
    def _list_docker_sync() -> str:
        try:
            res = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}} - {{.Status}}"],
                capture_output=True,
                text=True,
            )
            return (
                f"🐳 *Containers Rodando:*\n{res.stdout}"
                if res.stdout
                else "🐳 Nenhum container rodando."
            )
        except Exception:
            return "🐳 Docker não disponível."

    # ==================================================
    # AÇÃO PERIGOSA
    # ==================================================
    @staticmethod
    def reboot_device() -> str:
        subprocess.Popen("sleep 2 && sudo reboot", shell=True)
        return "🔄 Reiniciando o sistema."
