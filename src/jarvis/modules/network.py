import asyncio
import logging
import subprocess
import time
from typing import List, Dict, Any

import scapy.all as scapy
from wakeonlan import send_magic_packet
from mac_vendor_lookup import MacLookup

from jarvis.config import Config
from jarvis.core.utils import retry_with_backoff
from jarvis.database.persistence import Persistence

logger = logging.getLogger(__name__)


class NetworkModule:
    """
    NetworkModule

    RESPONSABILIDADES:
    - Operações de rede
    - Coleta RAW (memória)
    - Resposta HUMANA (chat)

    NÃO interpreta.
    NÃO classifica.
    """

    # ==================================================
    # RAW NETWORK DATA (PASSO 5)
    # ==================================================
    @staticmethod
    async def get_raw_snapshot() -> Dict[str, Any]:
        return await asyncio.to_thread(NetworkModule._get_raw_snapshot_sync)

    @staticmethod
    def _get_raw_snapshot_sync() -> Dict[str, Any]:
        devices: List[Dict[str, str]] = []

        try:
            arp = scapy.ARP(pdst="192.168.1.0/24")
            ether = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
            result = scapy.srp(ether / arp, timeout=2, verbose=0)[0]

            for element in result:
                devices.append({
                    "ip": element[1].psrc,
                    "mac": element[1].hwsrc
                })

        except Exception as e:
            logger.error(f"RAW network snapshot error: {e}")

        return {
            "timestamp": time.time(),
            "device_count": len(devices),
            "devices": devices,
        }

    # ==================================================
    # HUMANO — SCAN PARA CHAT
    # ==================================================
    @staticmethod
    async def scan_network(ip_range: str = "192.168.1.0/24") -> str:
        result = await asyncio.to_thread(
            NetworkModule._scan_network_human_sync,
            ip_range
        )

        if isinstance(result, str):
            return result

        if not result:
            return "⚠️ Nenhum dispositivo ativo encontrado."

        header = "🕵️‍♂️ Dispositivos na Rede:\n"
        return header + "\n".join(result)

    @staticmethod
    def _scan_network_human_sync(ip_range: str) -> List[str] | str:
        # Tenta duas vezes para garantir mais dispositivos
        try:
            # 1ª Tentativa (Rápida)
            arp = scapy.ARP(pdst=ip_range)
            ether = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
            result = scapy.srp(ether / arp, timeout=2, verbose=0)[0]

            # 2ª Tentativa (Se achou pouco, tenta mais lento)
            if len(result) < 3:
                 result = scapy.srp(ether / arp, timeout=4, verbose=0)[0]

        except PermissionError:
            return "❌ Permissão insuficiente para escanear a rede."
        except Exception as e:
            logger.error(f"Erro scan humano: {e}")
            return "❌ Erro ao escanear a rede."

        mac_lookup = MacLookup()
        try:
            mac_lookup.update_vendors()
        except Exception:
            pass

        devices = []

        # Sort by IP for cleaner list
        sorted_results = sorted(result, key=lambda x: int(x[1].psrc.split('.')[-1]))

        for element in sorted_results:
            ip = element[1].psrc
            mac = element[1].hwsrc

            # 1. Custom Name (Persistence)
            custom_name = Persistence.get_device_name(mac)

            # 2. Vendor Lookup
            try:
                vendor = mac_lookup.lookup(mac)
            except Exception:
                vendor = "Genérico"

            # Format: 🖥️ 192.168.1.52 (PC Marcelo) - Dell Inc.
            # OR:     🖥️ 192.168.1.50 (LG Innotek)

            display_name = custom_name if custom_name else vendor
            extra_info = f" - {vendor}" if custom_name else ""

            devices.append(f"🖥️ {ip} ({display_name}){extra_info}")

        return devices

    # ==================================================
    # HELPER: RESOLVE IP -> MAC
    # ==================================================
    @staticmethod
    async def resolve_mac_by_ip(ip: str) -> str | None:
        """
        Tenta resolver o MAC address de um IP específico usando ARP scan rápido.
        """
        # 1. Tenta cache rápido (Raw Snapshot) se for recente?
        # Por enquanto faz scan direto focado no IP para garantir.
        return await asyncio.to_thread(NetworkModule._resolve_mac_by_ip_sync, ip)

    @staticmethod
    def _resolve_mac_by_ip_sync(ip: str) -> str | None:
        try:
            arp = scapy.ARP(pdst=ip)
            ether = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
            result = scapy.srp(ether / arp, timeout=2, verbose=0)[0]

            if result:
                return result[0][1].hwsrc
        except Exception as e:
            logger.error(f"Erro ao resolver MAC para {ip}: {e}")
        return None

    # ==================================================
    # WAKE ON LAN
    # ==================================================
    @staticmethod
    @retry_with_backoff(retries=2)
    async def wake_pc() -> str:
        if not Config.PC_MAC or Config.PC_MAC == "00:00:00:00:00:00":
            return "❌ MAC do PC não configurado."

        send_magic_packet(Config.PC_MAC)
        return f"⚡ Wake-on-LAN enviado para `{Config.PC_MAC}`."

    # ==================================================
    # PING
    # ==================================================
    @staticmethod
    @retry_with_backoff()
    async def check_ping() -> str:
        return await asyncio.to_thread(NetworkModule._ping_sync)

    @staticmethod
    def _ping_sync() -> str:
        subprocess.check_call(
            ["ping", "-c", "1", "8.8.8.8"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return "🟢 Conectividade OK (ping 8.8.8.8)"

    # ==================================================
    # SPEEDTEST
    # ==================================================
    @staticmethod
    @retry_with_backoff(retries=1)
    async def run_speedtest() -> str:
        return await asyncio.to_thread(NetworkModule._speedtest_sync)

    @staticmethod
    def _speedtest_sync() -> str:
        res = subprocess.run(
            ["speedtest-cli", "--simple"],
            capture_output=True,
            text=True,
            check=True
        )
        return f"🚀 Speedtest:\n{res.stdout}"
