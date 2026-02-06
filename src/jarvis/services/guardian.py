import asyncio
import logging
from typing import Dict, Any, List

from jarvis.core.context_reader import ContextReader
from jarvis.core.context import ContextEngine

logger = logging.getLogger("services.guardian")


class GuardianService:
    """
    GuardianService — PASSO 7, 8 e 9

    RESPONSABILIDADES:
    - Monitorar estado do sistema e rede
    - Detectar anomalias técnicas
    - Gerar ALERTA + SUGESTÃO
    - Preparar ações para execução futura (com autorização)
    - NUNCA executar ações automaticamente
    """

    def __init__(
        self,
        application,
        chat_id: int,
        interval_seconds: int = 60,
    ):
        self.app = application
        self.chat_id = chat_id
        self.interval = interval_seconds
        self.running = False

    # ==================================================
    # LOOP PRINCIPAL
    # ==================================================
    async def start(self):
        if self.running:
            return

        self.running = True
        logger.info("🛡 GuardianService iniciado.")

        while self.running:
            try:
                await self.run_checks()
            except Exception:
                logger.exception("Erro no GuardianService")

            await asyncio.sleep(self.interval)

    # ==================================================
    # CHECKS
    # ==================================================
    async def run_checks(self):
        alerts: List[Dict[str, Any]] = []

        alerts += self.check_new_devices()
        alerts += self.check_unknown_devices()
        alerts += self.check_gap()
        alerts += self.check_system_anomaly()

        if alerts:
            await self.notify(alerts)

    # ==================================================
    # CHECKS INDIVIDUAIS
    # ==================================================
    def check_new_devices(self) -> List[Dict[str, Any]]:
        result = ContextReader.detect_new_devices(minutes_ago=30)

        if result.get("status") != "ok":
            return []

        alerts = []

        for mac in result.get("new_devices", []):
            alerts.append({
                "type": "new_device",
                "severity": "info",
                "message": "Novo dispositivo detectado na rede",
                "data": {"mac": mac},
                "suggested_action": {
                    "action_id": "classify_device",
                    "description": "Nomear e classificar dispositivo",
                    "payload": {"mac": mac},
                },
            })

        return alerts

    def check_unknown_devices(self) -> List[Dict[str, Any]]:
        result = ContextReader.detect_new_devices(minutes_ago=30)

        if result.get("status") != "ok":
            return []

        alerts = []

        for mac in result.get("unknown_devices", []):
            alerts.append({
                "type": "unknown_device",
                "severity": "warning",
                "message": "Dispositivo desconhecido na rede",
                "data": {"mac": mac},
                "suggested_action": {
                    "action_id": "block_device",
                    "description": "Bloquear dispositivo na rede",
                    "payload": {"mac": mac},
                },
            })

        return alerts

    def check_gap(self) -> List[Dict[str, Any]]:
        result = ContextReader.detect_gap(max_gap_minutes=5)

        if result.get("status") != "ok":
            return []

        if not result.get("exceeded"):
            return []

        return [{
            "type": "collection_gap",
            "severity": "critical",
            "message": "Possível queda de energia ou travamento",
            "data": {
                "gap_minutes": round(result.get("gap_minutes", 0), 2)
            },
            "suggested_action": {
                "action_id": "reboot_system",
                "description": "Reiniciar o sistema",
                "payload": {},
            },
        }]

    def check_system_anomaly(self) -> List[Dict[str, Any]]:
        result = ContextReader.compare_with_baseline()

        if result.get("status") != "ok":
            return []

        if result.get("normal"):
            return []

        return [{
            "type": "system_anomaly",
            "severity": "warning",
            "message": "Sistema fora do padrão normal",
            "data": result.get("diff"),
            "suggested_action": {
                "action_id": "inspect_system",
                "description": "Verificar status do sistema",
                "payload": {},
            },
        }]

    # ==================================================
    # NOTIFICAÇÃO
    # ==================================================
    async def notify(self, alerts: List[Dict[str, Any]]):
        for alert in alerts:
            # Salva ação pendente
            ContextEngine.set_pending_action(
                self.chat_id,
                alert["suggested_action"]
            )

            msg = (
                "🚨 *Alerta do Jarvis*\n\n"
                f"🧩 Tipo: `{alert['type']}`\n"
                f"⚠️ Severidade: *{alert['severity']}*\n\n"
                f"{alert['message']}\n\n"
                "💡 *Sugestão de ação:*\n"
                f"- {alert['suggested_action']['description']}\n\n"
                "👉 Responda *executar* para confirmar ou *cancelar*."
            )

            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=msg,
                parse_mode="Markdown",
            )
