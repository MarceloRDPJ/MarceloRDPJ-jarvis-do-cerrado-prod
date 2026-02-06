from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from core.context import ContextEngine
from database.persistence import Persistence


class ContextReader:
    """
    ContextReader — Leitura Técnica da Memória do Jarvis

    RESPONSABILIDADES (NUNCA VIOLAR):
    - Ler dados RAW
    - Comparar períodos
    - Retornar diferenças estruturadas
    - Detectar presença / ausência
    - Classificar dispositivos (conhecido / desconhecido)
    - Preparar dados para Guardian / Executor / Automations
    - NÃO interpretar
    - NÃO gerar texto humano
    - NÃO executar ações
    """

    # ==================================================
    # 🔐 DISPOSITIVOS CONHECIDOS (STATE)
    # ==================================================
    @staticmethod
    def register_device(mac: str, name: str, trusted: bool = True):
        """
        Registra ou atualiza um dispositivo conhecido.
        """
        devices = Persistence.get_state("devices:known", {})
        devices[mac.lower()] = {
            "name": name,
            "trusted": trusted,
            "updated_at": datetime.utcnow().isoformat(),
        }
        Persistence.set_state("devices:known", devices)

    @staticmethod
    def get_known_devices() -> Dict[str, Any]:
        """
        Retorna dispositivos conhecidos.
        """
        return Persistence.get_state("devices:known", {})

    @staticmethod
    def classify_device(mac: str) -> str:
        """
        Retorna classificação do dispositivo.
        """
        devices = ContextReader.get_known_devices()
        if mac.lower() in devices:
            return "trusted" if devices[mac.lower()]["trusted"] else "guest"
        return "unknown"

    # ==================================================
    # METADADOS GERAIS
    # ==================================================
    @staticmethod
    def metadata(minutes: int = 1440) -> Dict[str, Any]:
        snapshots = ContextEngine.get_recent_snapshots(minutes=minutes)

        if not snapshots:
            return {
                "status": "no_data",
                "window_minutes": minutes,
                "count": 0,
            }

        return {
            "status": "ok",
            "window_minutes": minutes,
            "count": len(snapshots),
            "first_timestamp": snapshots[-1]["timestamp"],
            "last_timestamp": snapshots[0]["timestamp"],
        }

    # ==================================================
    # SNAPSHOT ATUAL
    # ==================================================
    @staticmethod
    def current() -> Optional[Dict[str, Any]]:
        snaps = ContextEngine.get_recent_snapshots(minutes=5)
        return snaps[0] if snaps else None

    # ==================================================
    # DISPOSITIVOS ATUAIS (COM CLASSIFICAÇÃO)
    # ==================================================
    @staticmethod
    def current_devices() -> List[Dict[str, Any]]:
        """
        Retorna dispositivos da rede com classificação.
        """
        current = ContextReader.current()
        if not current:
            return []

        devices = current.get("network", {}).get("devices", [])
        result = []

        for d in devices:
            mac = d.get("mac", "").lower()
            result.append({
                "ip": d.get("ip"),
                "mac": mac,
                "classification": ContextReader.classify_device(mac),
            })

        return result

    # ==================================================
    # COMPARAÇÃO TEMPORAL
    # ==================================================
    @staticmethod
    def compare_with_past(minutes_ago: int = 60) -> Dict[str, Any]:
        current = ContextReader.current()
        reference = ContextEngine.get_snapshot_before(minutes_ago)

        if not current or not reference:
            return {
                "status": "insufficient_data",
                "reference_minutes_ago": minutes_ago,
            }

        diff = ContextEngine.diff_snapshots(current, reference)

        return {
            "status": "ok",
            "reference_minutes_ago": minutes_ago,
            "changed": bool(diff),
            "diff": diff,
        }

    # ==================================================
    # BASELINE
    # ==================================================
    @staticmethod
    def compare_with_baseline() -> Dict[str, Any]:
        baseline = ContextEngine.get_baseline()
        current = ContextReader.current()

        if not baseline:
            return {"status": "no_baseline"}

        if not current:
            return {"status": "no_current_data"}

        diff = ContextEngine.diff_snapshots(current, baseline)

        return {
            "status": "ok",
            "normal": not bool(diff),
            "diff": diff,
        }

    # ==================================================
    # DETECÇÃO DE NOVOS DISPOSITIVOS
    # ==================================================
    @staticmethod
    def detect_new_devices(minutes_ago: int = 30) -> Dict[str, Any]:
        """
        Detecta dispositivos novos ou desconhecidos.
        """
        current = ContextReader.current()
        past = ContextEngine.get_snapshot_before(minutes_ago)

        if not current or not past:
            return {"status": "insufficient_data"}

        current_macs = {
            d["mac"].lower()
            for d in current.get("network", {}).get("devices", [])
        }

        past_macs = {
            d["mac"].lower()
            for d in past.get("network", {}).get("devices", [])
        }

        new_macs = current_macs - past_macs

        unknown = [
            mac for mac in new_macs
            if ContextReader.classify_device(mac) == "unknown"
        ]

        return {
            "status": "ok",
            "new_devices": list(new_macs),
            "unknown_devices": unknown,
        }

    # ==================================================
    # DETECÇÃO DE AUSÊNCIA
    # ==================================================
    @staticmethod
    def detect_gap(max_gap_minutes: int = 5) -> Dict[str, Any]:
        current = ContextReader.current()
        if not current:
            return {"status": "no_data"}

        ts = datetime.fromisoformat(current["timestamp"])
        delta = datetime.utcnow() - ts

        return {
            "status": "ok",
            "gap_minutes": delta.total_seconds() / 60,
            "exceeded": delta > timedelta(minutes=max_gap_minutes),
        }

    # ==================================================
    # ROUTER
    # ==================================================
    @staticmethod
    def handle(params: Dict[str, Any]) -> Dict[str, Any]:
        mode = params.get("mode", "summary")

        if mode == "summary":
            return ContextReader.metadata(
                minutes=int(params.get("minutes", 1440))
            )

        if mode == "compare":
            return ContextReader.compare_with_past(
                minutes_ago=int(params.get("minutes_ago", 60))
            )

        if mode == "baseline":
            return ContextReader.compare_with_baseline()

        if mode == "devices":
            return {
                "status": "ok",
                "devices": ContextReader.current_devices(),
            }

        if mode == "new_devices":
            return ContextReader.detect_new_devices(
                minutes_ago=int(params.get("minutes_ago", 30))
            )

        if mode == "gap":
            return ContextReader.detect_gap(
                max_gap_minutes=int(params.get("max_gap", 5))
            )

        return {
            "status": "invalid_mode",
            "mode": mode,
            "available_modes": [
                "summary",
                "compare",
                "baseline",
                "devices",
                "new_devices",
                "gap",
            ],
        }
