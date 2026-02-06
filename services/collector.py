# -*- coding: utf-8 -*-

import asyncio
import logging
from datetime import datetime

from database.persistence import Persistence
from core.context import ContextEngine

from modules.system import SystemModule
from modules.network import NetworkModule

logger = logging.getLogger("services.collector")


class CollectorService:
    """
    Serviço de Coleta Automática do Jarvis.

    Responsabilidades:
    - Coletar dados periodicamente
    - Persistir dados brutos
    - Alimentar ContextEngine
    - NÃO interpretar
    - NÃO alertar
    """

    def __init__(self, interval_seconds: int = 60):
        self.interval = interval_seconds
        self.running = False

    async def start(self):
        """Inicia loop de coleta."""
        if self.running:
            return

        self.running = True
        logger.info("CollectorService iniciado.")

        while self.running:
            try:
                await self.collect()
            except Exception:
                logger.exception("Erro durante coleta automática")

            await asyncio.sleep(self.interval)

    async def collect(self):
        """
        Coleta um snapshot completo do sistema.
        """
        timestamp = datetime.utcnow().isoformat()

        snapshot = {
            "timestamp": timestamp,
            "system": {},
            "network": {}
        }

        # =========================
        # SYSTEM
        # =========================
        try:
            snapshot["system"] = await SystemModule.get_raw_status()
        except Exception:
            logger.exception("Falha ao coletar system status")

        # =========================
        # NETWORK
        # =========================
        try:
            snapshot["network"] = await NetworkModule.get_raw_snapshot()
        except Exception:
            logger.exception("Falha ao coletar network snapshot")

        # =========================
        # PERSISTÊNCIA
        # =========================
        try:
            Persistence.save_snapshot(snapshot)
        except Exception:
            logger.exception("Falha ao salvar snapshot")

        # =========================
        # CONTEXTO
        # =========================
        try:
            ContextEngine.update_baseline(snapshot)
        except Exception:
            logger.exception("Falha ao atualizar baseline")

        logger.debug("Snapshot coletado com sucesso.")
