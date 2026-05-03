"""
MCP Handler — Model Context Protocol for Jarvis do Cerrado
===========================================================
Implementa o protocolo MCP (Model Context Protocol) para permitir
que modelos de IA (LLMs) interajam com o Jarvis de forma estruturada.

Fornece tools, resources e prompts que modelos podem usar.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("api.mcp")


class MCPHandler:
    """
    Model Context Protocol (MCP) Handler.
    
    Permite que LLMs e agentes de IA interajam com o Jarvis
    através de um protocolo padronizado de tools e resources.
    """

    def __init__(self, app_state):
        self.app = app_state
        self.tools = self._build_tools()
        self.resources = self._build_resources()

    def _build_tools(self) -> List[Dict[str, Any]]:
        """Build the list of available MCP tools."""
        return [
            {
                "name": "system_status",
                "description": "Get real-time system status (CPU, RAM, Disk, Temp, Uptime)",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "network_scan",
                "description": "Scan local network for connected devices",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "depth": {
                            "type": "string",
                            "enum": ["quick", "standard", "deep"],
                            "description": "Scan depth",
                        }
                    },
                },
            },
            {
                "name": "fan_control",
                "description": "Control the Raspberry Pi fan",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["on", "off", "auto", "speed"],
                            "description": "Action to perform",
                        },
                        "speed": {
                            "type": "integer",
                            "description": "Fan speed 0-100 (PWM)",
                            "minimum": 0,
                            "maximum": 100,
                        },
                    },
                    "required": ["action"],
                },
            },
            {
                "name": "send_notification",
                "description": "Send a notification via Telegram",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message text to send",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "normal", "high"],
                            "description": "Notification priority",
                        },
                    },
                    "required": ["message"],
                },
            },
            {
                "name": "block_site",
                "description": "Block a website or domain via AdGuard",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "Domain to block (e.g., youtube.com)",
                        }
                    },
                    "required": ["domain"],
                },
            },
            {
                "name": "run_speedtest",
                "description": "Run an internet speed test",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "get_hydration_status",
                "description": "Get today's hydration progress",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "list_reminders",
                "description": "List all active reminders",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "create_reminder",
                "description": "Create a new reminder",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Reminder text"},
                        "time": {"type": "string", "description": "Time for reminder (e.g., 14:30)"},
                        "recurring": {"type": "boolean", "description": "Is this recurring?"},
                    },
                    "required": ["text", "time"],
                },
            },
            {
                "name": "get_network_stats",
                "description": "Get AdGuard network statistics",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "docker_ps",
                "description": "List running Docker containers",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "reboot_system",
                "description": "Reboot the Raspberry Pi (requires confirmation)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "confirm": {
                            "type": "boolean",
                            "description": "Must be true to reboot",
                        }
                    },
                    "required": ["confirm"],
                },
            },
        ]

    def _build_resources(self) -> List[Dict[str, Any]]:
        """Build the list of available MCP resources."""
        return [
            {
                "uri": "jarvis://system/status",
                "name": "System Status",
                "description": "Real-time system metrics",
                "mime_type": "application/json",
            },
            {
                "uri": "jarvis://network/devices",
                "name": "Network Devices",
                "description": "List of connected network devices",
                "mime_type": "application/json",
            },
            {
                "uri": "jarvis://network/stats",
                "name": "Network Statistics",
                "description": "AdGuard DNS query statistics",
                "mime_type": "application/json",
            },
            {
                "uri": "jarvis://hydration/today",
                "name": "Today's Hydration",
                "description": "Current day hydration progress",
                "mime_type": "application/json",
            },
            {
                "uri": "jarvis://bot/personality",
                "name": "Bot Personality",
                "description": "Current personality configuration",
                "mime_type": "application/json",
            },
            {
                "uri": "jarvis://system/logs",
                "name": "System Logs",
                "description": "Recent system event logs",
                "mime_type": "application/json",
            },
        ]

    def list_tools(self) -> List[Dict[str, Any]]:
        """Get all available MCP tools."""
        return self.tools

    def list_resources(self) -> List[Dict[str, Any]]:
        """Get all available MCP resources."""
        return self.resources

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Execute an MCP tool by name with given parameters."""
        from jarvis.modules.system import SystemModule
        from jarvis.modules.network import NetworkModule
        from jarvis.modules.hydration import HydrationModule
        from jarvis.config import Config

        # System tools
        if tool_name == "system_status":
            return await SystemModule.get_raw_status()

        elif tool_name == "network_scan":
            depth = parameters.get("depth", "standard")
            if depth == "deep":
                devices = await NetworkModule.scan_network_deep()
            else:
                devices = await NetworkModule.scan_network()
            return {"devices": devices, "count": len(devices)}

        elif tool_name == "fan_control":
            fan_service = getattr(self.app, "fan_service", None)
            if not fan_service or not fan_service.fan:
                return {"error": "Fan service not available"}
            
            action = parameters.get("action", "status")
            if action == "on":
                fan_service.fan.on()
                fan_service.manual_override = True
                return {"state": "on", "mode": "manual"}
            elif action == "off":
                fan_service.fan.off()
                fan_service.manual_override = True
                return {"state": "off", "mode": "manual"}
            elif action == "auto":
                fan_service.manual_override = False
                return {"mode": "auto"}
            elif action == "speed":
                speed = max(0, min(100, parameters.get("speed", 50)))
                if speed == 0:
                    fan_service.fan.off()
                else:
                    if hasattr(fan_service.fan, 'value'):
                        fan_service.fan.value = speed / 100.0
                    else:
                        fan_service.fan.on()
                fan_service.manual_override = True
                return {"state": "on" if speed > 0 else "off", "speed": speed}
            else:
                return {
                    "state": "on" if fan_service.fan.is_active else "off",
                    "manual_override": fan_service.manual_override,
                    "speed": getattr(fan_service, 'speed_percent', 100),
                }

        elif tool_name == "send_notification":
            bot = getattr(self.app, "bot_app", None)
            if bot and Config.ALLOWED_USER_ID:
                message = parameters.get("message", "")
                priority = parameters.get("priority", "normal")
                prefix = {"high": "🔴 ", "normal": "", "low": "ℹ️ "}.get(priority, "")
                await bot.bot.send_message(
                    chat_id=Config.ALLOWED_USER_ID,
                    text=f"{prefix}{message}",
                )
                return {"sent": True}
            return {"error": "Bot not available"}

        elif tool_name == "block_site":
            from jarvis.modules.adguard import AdGuardClient
            domain = parameters.get("domain", "")
            if not domain:
                return {"error": "Domain required"}
            result = await AdGuardClient.block_client(domain, name=f"Blocked: {domain}")
            return result

        elif tool_name == "run_speedtest":
            result = await NetworkModule.run_speedtest()
            return result

        elif tool_name == "get_hydration_status":
            result = HydrationModule.get_status_message(Config.ALLOWED_USER_ID)
            return result

        elif tool_name == "list_reminders":
            from jarvis.core.flows import RemindersFlow
            result = RemindersFlow.list_reminders(Config.ALLOWED_USER_ID)
            return result

        elif tool_name == "create_reminder":
            from jarvis.core.flows import RemindersFlow
            params = {
                "text": parameters.get("text", ""),
                "time": parameters.get("time", ""),
                "recurring": parameters.get("recurring", False),
            }
            result = RemindersFlow.start_flow(Config.ALLOWED_USER_ID, params)
            return result

        elif tool_name == "get_network_stats":
            from jarvis.modules.adguard import AdGuardClient
            stats = await AdGuardClient.get_stats()
            top = await AdGuardClient.get_top_clients(limit=5)
            return {"stats": stats, "top_clients": top}

        elif tool_name == "docker_ps":
            result = await SystemModule.list_docker()
            return result

        elif tool_name == "reboot_system":
            if parameters.get("confirm") is True:
                result = SystemModule.reboot_device()
                return {"status": "rebooting", "message": result}
            return {"error": "Reboot requires confirmation"}

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    async def get_resource(self, uri: str) -> Optional[Dict[str, Any]]:
        """Get the content of an MCP resource by URI."""
        from jarvis.modules.system import SystemModule
        from jarvis.modules.network import NetworkModule
        from jarvis.config import Config

        if uri == "jarvis://system/status":
            data = await SystemModule.get_raw_status()
            return {"uri": uri, "data": data}

        elif uri == "jarvis://network/devices":
            devices = await NetworkModule.scan_network()
            return {"uri": uri, "data": {"devices": devices}}

        elif uri == "jarvis://network/stats":
            from jarvis.modules.adguard import AdGuardClient
            stats = await AdGuardClient.get_stats()
            return {"uri": uri, "data": stats}

        elif uri == "jarvis://hydration/today":
            from jarvis.modules.hydration import HydrationModule
            from jarvis.database.persistence import Persistence
            volume = Persistence.get_hydration_volume_today(Config.ALLOWED_USER_ID)
            count = Persistence.get_hydration_count_today(Config.ALLOWED_USER_ID)
            return {"uri": uri, "data": {"volume_ml": volume, "count": count}}

        elif uri == "jarvis://bot/personality":
            from jarvis.core.personality import Personality
            categories = {}
            for attr in dir(Personality):
                if attr.isupper() and not attr.startswith('_'):
                    val = getattr(Personality, attr)
                    if isinstance(val, (list, dict)):
                        categories[attr] = val
            return {"uri": uri, "data": categories}

        elif uri == "jarvis://system/logs":
            from jarvis.database.persistence import Persistence
            logs = Persistence.get_recent_snapshots(1440, limit=50)
            return {"uri": uri, "data": {"logs": logs}}

        return None
