import psutil
import time
from datetime import datetime, timedelta
from database.persistence import Persistence

# =============================================================================
# CONFIGURA\xc7\xc3O BASE (Raspberry Pi 3B)
# =============================================================================

# Consumo m\xe9dio estimado (Watts)
RPI_IDLE_WATTS = 2.5
RPI_LOAD_WATTS = 5.5

class EnergyService:
    """
    Servi\xe7o de consumo de energia.
    N\xe3o usa IA.
    Baseado em m\xe9tricas reais do sistema.
    """

    @staticmethod
    def _estimate_current_watts() -> float:
        """
        Estima consumo atual baseado em carga da CPU.
        """
        cpu_load = psutil.cpu_percent(interval=1)

        # interpola\xe7\xe3o simples
        watts = RPI_IDLE_WATTS + (
            (cpu_load / 100) * (RPI_LOAD_WATTS - RPI_IDLE_WATTS)
        )
        return round(watts, 2)

    @staticmethod
    def log_energy_sample():
        """
        Salva amostra de consumo.
        Ideal rodar a cada 5 ou 10 minutos via job.
        """
        watts = EnergyService._estimate_current_watts()
        timestamp = datetime.now().isoformat()

        Persistence.log_event(
            type="energy.sample",
            source="energy",
            payload={
                "watts": watts,
                "timestamp": timestamp
            }
        )

    @staticmethod
    def get_energy_today() -> str:
        """
        Retorna consumo estimado do dia.
        """
        events = Persistence.get_events_by_type("energy.sample", limit=500)

        if not events:
            return "? Ainda n\xe3o tenho dados suficientes de energia hoje."

        total_wh = 0.0
        for e in events:
            total_wh += e["payload"]["watts"] * (5 / 60)  # 5 min = 1/12 hora

        kwh = total_wh / 1000
        return (
            "? *Consumo de energia hoje:*\n"
            f"- Aproximadamente: `{kwh:.3f} kWh`\n"
            f"- Baseado no uso real do Raspberry Pi"
        )

    @staticmethod
    def get_energy_month() -> str:
        """
        Retorna consumo estimado mensal.
        """
        events = Persistence.get_events_by_type("energy.sample", limit=5000)

        if not events:
            return "? Ainda n\xe3o tenho dados suficientes este m\xeas."

        total_wh = 0.0
        for e in events:
            total_wh += e["payload"]["watts"] * (5 / 60)

        kwh = total_wh / 1000
        return (
            "? *Consumo estimado do m\xeas:*\n"
            f"- `{kwh:.2f} kWh`\n"
            f"- Estimativa baseada no hist\xf3rico do sistema"
        )
