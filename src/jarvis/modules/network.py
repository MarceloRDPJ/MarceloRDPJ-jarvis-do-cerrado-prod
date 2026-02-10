import asyncio
import logging
import subprocess
import time
import socket
import struct
from typing import List, Dict, Any, Set

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
    # SCANNING HELPERS (mDNS / SSDP)
    # ==================================================
    @staticmethod
    def _scan_ssdp(timeout: float = 2.0) -> Set[str]:
        """
        Envia M-SEARCH (SSDP) para descobrir dispositivos UPnP (Smart TVs, Routers, etc).
        Retorna conjunto de IPs.
        """
        ips = set()
        msg = (
            'M-SEARCH * HTTP/1.1\r\n'
            'HOST:239.255.255.250:1900\r\n'
            'ST:ssdp:all\r\n'
            'MX:2\r\n'
            'MAN:"ssdp:discover"\r\n'
            '\r\n'
        ).encode('utf-8')

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(timeout)
        try:
            sock.sendto(msg, ('239.255.255.250', 1900))
            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = sock.recvfrom(65507)
                    ips.add(addr[0])
                except socket.timeout:
                    break
                except Exception:
                    break
        except Exception as e:
            logger.error(f"SSDP Scan Error: {e}")
        finally:
            sock.close()

        return ips

    @staticmethod
    def _scan_mdns(timeout: float = 2.0) -> Set[str]:
        """
        Envia query mDNS para descobrir dispositivos Bonjour/ZeroConf (Apple, Google, IoT).
        Retorna conjunto de IPs.
        """
        ips = set()
        # Query genérica para _services._dns-sd._udp.local (Standard Discovery)
        # Header: ID=0, Flags=0, QDCOUNT=1, ANCOUNT=0...
        # QNAME: \x09_services\x07_dns-sd\x04_udp\x05local\x00
        # QTYPE: 0x000C (PTR), QCLASS: 0x0001 (IN)
        packet = (
            b'\x00\x00'  # Transaction ID
            b'\x00\x00'  # Flags
            b'\x00\x01'  # Questions
            b'\x00\x00'  # Answer RRs
            b'\x00\x00'  # Authority RRs
            b'\x00\x00'  # Additional RRs
            b'\x09_services\x07_dns-sd\x04_udp\x05local\x00'
            b'\x00\x0c'  # Type PTR
            b'\x00\x01'  # Class IN
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(timeout)
        # Necessário para multicast
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

        try:
            sock.sendto(packet, ('224.0.0.251', 5353))
            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = sock.recvfrom(65507)
                    ips.add(addr[0])
                except socket.timeout:
                    break
                except Exception:
                    break
        except Exception as e:
            logger.error(f"mDNS Scan Error: {e}")
        finally:
            sock.close()

        return ips

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
            # Simple ARP for raw snapshot (fast)
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
    # HUMANO — SCAN PARA CHAT (HÍBRIDO)
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

        header = f"🕵️‍♂️ Dispositivos na Rede ({len(result)} encontrados):\n"
        return header + "\n".join(result)

    @staticmethod
    def _scan_network_human_sync(ip_range: str) -> List[str] | str:
        found_devices = {} # Map IP -> MAC

        # 1. ARP Scan (Base)
        try:
            arp = scapy.ARP(pdst=ip_range)
            ether = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
            # Increased timeout for robustness
            result = scapy.srp(ether / arp, timeout=3, verbose=0)[0]

            for sent, received in result:
                found_devices[received.psrc] = received.hwsrc

        except Exception as e:
            logger.error(f"ARP Scan Error: {e}")
            # Continue to other methods even if ARP fails (e.g. permission issue)

        # 2. Hybrid Discovery (SSDP + mDNS)
        # Finds IPs of smart devices that might ignore ARP broadcast or be sleepy
        try:
            ssdp_ips = NetworkModule._scan_ssdp(timeout=2.5)
            mdns_ips = NetworkModule._scan_mdns(timeout=2.5)
            hybrid_ips = ssdp_ips.union(mdns_ips)

            # Remove IPs we already have MACs for
            unknown_mac_ips = [ip for ip in hybrid_ips if ip not in found_devices]

            # 3. Targeted ARP Resolution for unknown IPs
            # Unicast ARP is often more reliable than broadcast for specific targets
            for ip in unknown_mac_ips:
                try:
                    mac = NetworkModule._resolve_mac_by_ip_sync(ip)
                    if mac:
                        found_devices[ip] = mac
                except:
                    pass

        except Exception as e:
            logger.error(f"Hybrid Scan Error: {e}")

        if not found_devices:
             return []

        # 4. Enrichment (Vendor + Custom Name)
        mac_lookup = MacLookup()
        try:
            # Update vendors strictly if older than X?
            # Doing it every time slows down. Let's assume it's cached or updated elsewhere.
            # mac_lookup.update_vendors()
            pass
        except Exception:
            pass

        output_list = []

        # Sort by IP
        sorted_ips = sorted(found_devices.keys(), key=lambda x: int(x.split('.')[-1]) if x.count('.')==3 else 0)

        for ip in sorted_ips:
            mac = found_devices[ip]

            # 1. Custom Name (Persistence)
            custom_name = Persistence.get_device_name(mac)

            # 2. Vendor Lookup
            try:
                vendor = mac_lookup.lookup(mac)
            except Exception:
                vendor = "Genérico"

            # Icon selection based on vendor (Simple Heuristics)
            icon = "🖥️"
            v_lower = vendor.lower()
            if "apple" in v_lower: icon = "🍎"
            elif "google" in v_lower: icon = "🤖"
            elif "espressif" in v_lower or "tuya" in v_lower: icon = "🔌"
            elif "intel" in v_lower or "dell" in v_lower or "hp" in v_lower: icon = "💻"
            elif "samsung" in v_lower or "lg" in v_lower: icon = "📺"

            # Formatting
            if custom_name:
                # 🖥️ 192.168.1.5 - TV Sala (Samsung)
                line = f"{icon} `{ip}` — *{custom_name}* ({vendor})"
            else:
                # 🖥️ 192.168.1.5 - Samsung Electronics
                line = f"{icon} `{ip}` — _{vendor}_"

            output_list.append(line)

        return output_list

    # ==================================================
    # HELPER: RESOLVE IP -> MAC
    # ==================================================
    @staticmethod
    async def resolve_mac_by_ip(ip: str) -> str | None:
        """
        Tenta resolver o MAC address de um IP específico usando ARP scan rápido.
        """
        return await asyncio.to_thread(NetworkModule._resolve_mac_by_ip_sync, ip)

    @staticmethod
    def _resolve_mac_by_ip_sync(ip: str) -> str | None:
        try:
            arp = scapy.ARP(pdst=ip)
            ether = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
            # Unicast/Targeted ARP usually responds faster
            result = scapy.srp(ether / arp, timeout=1, verbose=0)[0]

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
        try:
            # --secure is often needed for SSL issues
            res = subprocess.run(
                ["speedtest-cli", "--simple", "--secure"],
                capture_output=True,
                text=True,
                check=True,
                timeout=45 # Timeout to avoid hanging
            )
            return f"🚀 *Velocidade da Internet:*\n\n{res.stdout}"
        except subprocess.TimeoutExpired:
            return "❌ O teste demorou demais e foi cancelado."
        except subprocess.CalledProcessError as e:
            logger.error(f"Speedtest failed: {e.stderr}")
            return "❌ Falha ao rodar speedtest. Tente novamente mais tarde."
        except Exception as e:
            return f"❌ Erro inesperado no teste: {e}"
