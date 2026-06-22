import psutil
import time
from datetime import datetime, timedelta, timezone
from jarvis.database.persistence import Persistence
from jarvis.core.events import Event

# -*- coding: utf-8 -*-

# =============================================================================
# CONFIGURAÇÃO BASE (Raspberry Pi 3B)
# =============================================================================

# Consumo médio estimado (Watts)
RPI_IDLE_WATTS = 2.5
RPI_LOAD_WATTS = 5.5

class EnergyService:
    """
    Serviço de consumo de energia.
    Não usa IA.
    Baseado em métricas reais do sistema.
    """

    @staticmethod
    def _estimate_current_watts() -> float:
        """
        Estima consumo atual baseado em carga da CPU.
        """
        cpu_load = psutil.cpu_percent(interval=1)

        # interpolação simples
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
        timestamp = datetime.now(timezone.utc).isoformat()

        Persistence.log_event(
            Event(type="energy.sample", source="energy", payload={
                "watts": watts,
                "timestamp": timestamp
            })
        )

    @staticmethod
    def get_energy_today() -> str:
        """
        Retorna consumo estimado do dia.
        """
        since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        events = Persistence.get_events_by_type("energy.sample", limit=500, since=since)

        if not events:
            return "? Ainda não tenho dados suficientes de energia hoje."

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
        now = datetime.now(timezone.utc)
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        events = Persistence.get_events_by_type("energy.sample", limit=5000, since=since)

        if not events:
            return "? Ainda não tenho dados suficientes este mês."

        total_wh = 0.0
        for e in events:
            total_wh += e["payload"]["watts"] * (5 / 60)

        kwh = total_wh / 1000
        return (
            "? *Consumo estimado do mês:*\n"
            f"- `{kwh:.2f} kWh`\n"
            f"- Estimativa baseada no histórico do sistema"
        )
