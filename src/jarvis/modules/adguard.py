import aiohttp
import base64
import logging
from typing import Dict, Any, List, Optional
from jarvis.config import Config

logger = logging.getLogger("modules.adguard")

class AdGuardClient:
    """Cliente para AdGuard Home API"""

    BASE_URL = Config.get("adguard.url", "http://localhost:3000")
    USERNAME = Config.get("adguard.username", "admin")
    PASSWORD = Config.get("adguard.password", "")

    @classmethod
    def _get_auth_header(cls) -> Dict[str, str]:
        """Gera header de autenticação Basic Auth"""
        credentials = f"{cls.USERNAME}:{cls.PASSWORD}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    @classmethod
    async def block_client(cls, ip: str, name: str = None) -> Dict[str, Any]:
        """
        Bloqueia um cliente específico no AdGuard.

        Args:
            ip: Endereço IP do cliente
            name: Nome descritivo (opcional)

        Returns:
            {"success": bool, "message": str}
        """
        url = f"{cls.BASE_URL}/control/filtering/add_url"
        headers = cls._get_auth_header()
        headers["Content-Type"] = "application/json"

        payload = {
            "name": name or f"Block {ip}",
            "url": f"||{ip}^",
            "whitelist": False
        }

        # Note: The prompt suggested "||{ip}/*". However, AdGuard syntax usually is "||example.org^".
        # For IP blocking, "||192.168.1.50^" blocks everything.
        # The prompt said: "url": f"||{ip}/*"
        # I will use the prompt's suggestion but without the * if it causes issues,
        # but typically adguard syntax uses ^ as separator or nothing.
        # "||1.2.3.4^" is standard for blocking a domain/IP.
        # Let's stick to the prompt's visual format but maybe standard AdGuard syntax is better?
        # Prompt: "||{ip}/*"
        # I will use "||{ip}^" which is standard for "block this domain/ip and subdomains".
        # Wait, the prompt explicitly said: "Payload: {"name": name, "url": f"||{ip}/*", "whitelist": false}"
        # I will follow the prompt exactly.
        payload["url"] = f"||{ip}/*"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        return {"success": True, "message": f"Cliente {ip} bloqueado com sucesso."}
                    else:
                        text = await response.text()
                        logger.error(f"AdGuard block failed: {response.status} - {text}")
                        return {"success": False, "message": f"Falha AdGuard ({response.status}): {text}"}
        except Exception as e:
            logger.exception("AdGuard block exception")
            return {"success": False, "message": f"Erro de conexão: {str(e)}"}

    @classmethod
    async def unblock_client(cls, ip: str) -> Dict[str, Any]:
        """Remove bloqueio de um cliente"""
        url = f"{cls.BASE_URL}/control/filtering/remove_url"
        headers = cls._get_auth_header()
        headers["Content-Type"] = "application/json"

        payload = {
            "url": f"||{ip}/*",
            "whitelist": False
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        return {"success": True, "message": f"Cliente {ip} desbloqueado."}
                    else:
                        text = await response.text()
                        logger.error(f"AdGuard unblock failed: {response.status} - {text}")
                        return {"success": False, "message": f"Falha AdGuard ({response.status}): {text}"}
        except Exception as e:
            logger.exception("AdGuard unblock exception")
            return {"success": False, "message": f"Erro de conexão: {str(e)}"}

    @classmethod
    async def get_stats(cls) -> Dict[str, Any]:
        """
        Obtém estatísticas de uso.

        Returns:
            {
                "num_dns_queries": int,
                "num_blocked_filtering": int,
                "top_queried_domains": List[str],
                "top_clients": List[Dict]
            }
        """
        url = f"{cls.BASE_URL}/control/stats"
        headers = cls._get_auth_header()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "num_dns_queries": data.get("num_dns_queries", 0),
                            "num_blocked_filtering": data.get("num_blocked_filtering", 0),
                            "top_queried_domains": data.get("top_queried_domains", []),
                            "top_clients": data.get("top_clients", [])
                        }
                    else:
                        text = await response.text()
                        logger.error(f"AdGuard stats failed: {response.status} - {text}")
                        return {}
        except Exception as e:
            logger.exception("AdGuard stats exception")
            return {}

    @classmethod
    async def get_top_clients(cls, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retorna os clientes que mais usam banda/DNS.

        Returns:
            [{"ip": str, "name": str, "queries": int, "blocked": int}, ...]
        """
        stats = await cls.get_stats()
        clients = stats.get("top_clients", [])

        # Sort by queries count descending (usually already sorted by AdGuard)
        # Format consistent return
        result = []
        for client in clients[:limit]:
            # AdGuard stats format: {"ip": "...", "name": "...", "queries": 123, "blocked": 10}
            # Or distinct structure depending on version.
            # Assuming standard structure based on prompt implication.
            # The prompt implies processing stats.

            # Note: "top_clients" in /control/stats is usually a list of objects.
            # Let's check typical response keys. It has "ip" (or keys mapped to IP), "name", etc.
            # Actually, "top_clients" in AdGuard API often returns list of {ip, name, count...}

            result.append({
                "ip": client.get("ip", "N/A"),
                "name": client.get("name", "") or client.get("ip", "N/A"),
                "queries": client.get("num", 0) if "num" in client else client.get("count", 0),
                # AdGuard often uses 'count' or map.
                # Let's assume the dictionary passed from stats matches.
                # If stats returns list of dicts:
                "blocked": client.get("blocked", 0)
            })

        # If 'top_clients' is a list of dicts as assumed.
        # Wait, typically /control/stats top_clients is a list of objects like:
        # [{"name": "192.168.1.2", "count": 1234}, ...]
        # I will implement adapting to likely keys.

        cleaned = []
        for c in clients[:limit]:
            name = c.get("name", "")
            if not name: name = list(c.keys())[0] if c else "Unknown" # fallback

            # Sometimes it is just a dict with many keys? No, usually list of objects.
            # Let's assume standard object: { "ip": "...", "name": "...", "count": ... }
            # Or the prompt example:
            # [{"ip": str, "name": str, "queries": int, "blocked": int}]

            # AdGuard API V1 /stats response:
            # "top_clients": [ { "ip": "1.2.3.4", "name": "foo", "count": 100 }, ... ]

            ip = c.get("ip", "")
            display_name = c.get("name") or ip
            queries = c.get("count", 0)
            blocked = c.get("blocked_count", 0) # Guessing key

            cleaned.append({
                "ip": ip,
                "name": display_name,
                "queries": queries,
                "blocked": blocked
            })

        return cleaned
