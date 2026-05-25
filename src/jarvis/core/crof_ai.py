"""
CrofAI Engine — Fallback cognitivo ECONÔMICO.
Só chamado quando Rules + IntentEngine + LocalBrain falham.
OpenAI-compatible (https://crof.ai/v1).
"""

import json
import logging
from typing import Dict, Any, Optional
from openai import OpenAI
from jarvis.database.persistence import Persistence
from datetime import datetime, timedelta

logger = logging.getLogger("core.crof_ai")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Get current system health: CPU, RAM, temperature, disk, uptime",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_internet",
            "description": "Check if internet is online and current latency",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hydration_status",
            "description": "Get today's water intake progress",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List all active reminders and tasks",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_devices",
            "description": "List devices currently connected to the local network",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_message",
            "description": "Send a proactive message to the user via Telegram (use sparingly)",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message text to send"
                    }
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wake_pc",
            "description": "Send Wake-on-LAN magic packet to turn on the PC",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_adguard_stats",
            "description": "Get AdGuard Home DNS query statistics and blocked threats",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

SYSTEM_PROMPT = (
    "Jarvis do Cerrado, assistente do Marcelo. "
    "Tom goiano leve, direto, util. Maximo 2 frases. "
    "Use tools para dados. Nao invente."
)


class CrofAIEngine:

    MODEL_PRICING = {
        "qwen3.5-9b": {"input": 0.04, "output": 0.008},
        "glm-4.7-flash": {"input": 0.04, "output": 0.008},
        "deepseek-v4-flash": {"input": 0.12, "output": 0.003},
        "gemma-4-31b-it": {"input": 0.10, "output": 0.02},
        "kimi-k2.5": {"input": 0.35, "output": 0.07},
    }

    def __init__(self, api_key: str, model: str = "qwen3.5-9b"):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://crof.ai/v1"
        )
        self.model = model
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        self.disabled_until = None
        self._tool_map = {
            "get_system_status": self._get_system_status,
            "check_internet": self._check_internet,
            "get_hydration_status": self._get_hydration_status,
            "list_reminders": self._list_reminders,
            "get_network_devices": self._get_network_devices,
            "send_telegram_message": self._send_telegram_message,
            "wake_pc": self._wake_pc,
            "get_adguard_stats": self._get_adguard_stats,
        }
        logger.info(f"CrofAI Engine ativado (modelo: {model})")

    async def process(self, user_text: str, chat_id: int = None) -> Optional[Dict[str, Any]]:
        if self.disabled_until:
            if datetime.now() >= self.disabled_until:
                self.consecutive_failures = 0
                self.disabled_until = None
            else:
                return None
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text}
                ],
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=100,
                temperature=0.3,
            )

            if response.usage:
                pt = response.usage.prompt_tokens
                ct = response.usage.completion_tokens
                tt = response.usage.total_tokens
                pricing = self.MODEL_PRICING.get(self.model, {"input": 0.04, "output": 0.008})
                cost = (pt * pricing["input"] + ct * pricing["output"]) / 1_000_000
                Persistence.log_token_usage(self.model, pt, ct, tt, cost, success=True)

            msg = response.choices[0].message

            if msg.tool_calls:
                results = []
                for tc in msg.tool_calls:
                    handler = self._tool_map.get(tc.function.name)
                    if handler:
                        r = await handler(**json.loads(tc.function.arguments))
                        results.append(str(r))

                response_text = (msg.content or "").strip()
                if not response_text:
                    response_text = " | ".join(results) if results else "Pronto."
            else:
                response_text = msg.content

            if response_text and response_text.strip():
                return {
                    "intent": "chat",
                    "response": response_text.strip(),
                    "text": user_text,
                    "source": "crof_ai",
                    "confidence": 0.85
                }

        except Exception as e:
            logger.error(f"CrofAI error: {e}")
            Persistence.log_api_error("crof_ai", str(e))
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.disabled_until = datetime.now() + timedelta(hours=1)
                logger.warning(f"CrofAI auto-desativado ate {self.disabled_until}")

        return None

    async def _get_system_status(self) -> str:
        from jarvis.modules.system import SystemModule
        raw = await SystemModule.get_raw_status()
        t = f"{raw['temperature_c']}C" if raw.get('temperature_c') else "N/A"
        return json.dumps({
            "cpu": f"{raw['cpu_percent']}%",
            "ram": f"{raw['memory']['percent']}%",
            "temp": t,
            "uptime": str(__import__('datetime').timedelta(seconds=raw['uptime_seconds'])),
            "disk": f"{raw['disk']['percent']}%"
        })

    async def _check_internet(self) -> str:
        from jarvis.modules.network import NetworkModule
        m = await NetworkModule.get_ping_metrics()
        return json.dumps({"status": "online", "latency_ms": m.get('latency_ms')} if m.get('success') else {"status": "offline"})

    async def _get_hydration_status(self) -> str:
        from jarvis.modules.hydration import HydrationModule
        from jarvis.config import Config
        return HydrationModule.get_status_message(Config.ALLOWED_USER_ID)

    async def _list_reminders(self) -> str:
        from jarvis.core.flows import RemindersFlow
        from jarvis.config import Config
        return RemindersFlow.list_reminders(Config.ALLOWED_USER_ID)

    async def _get_network_devices(self) -> str:
        from jarvis.modules.network import NetworkModule
        d = await NetworkModule.scan_network()
        return str(d)

    async def _send_telegram_message(self, message: str) -> str:
        return json.dumps({"action": "send_message", "message": message})

    async def _wake_pc(self) -> str:
        from jarvis.modules.network import NetworkModule
        from jarvis.config import Config
        r = await NetworkModule.wake_on_lan(Config.PC_MAC)
        return json.dumps(r)

    async def _get_adguard_stats(self) -> str:
        from jarvis.modules.adguard import AdGuardClient
        s = await AdGuardClient.get_stats()
        return json.dumps(s)
