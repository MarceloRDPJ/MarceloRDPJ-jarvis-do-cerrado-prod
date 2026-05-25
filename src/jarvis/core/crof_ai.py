"""
CrofAI Engine — Fallback cognitivo ECONÔMICO.
Só chamado quando Rules + IntentEngine + LocalBrain falham.
OpenAI-compatible (https://crof.ai/v1).
"""

import json
import logging
from typing import Dict, Any, Optional
from openai import OpenAI

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
    "Você é Jarvis do Cerrado, assistente pessoal, amigo e secretario do Marcelo. "
    "Tom goiano leve, direto, util. Maximo 2 frases. "
    "Use as ferramentas disponiveis quando precisar de informacoes ou executar acoes. "
    "Nunca invente informacoes — se nao sabe, use uma ferramenta para descobrir."
)


class CrofAIEngine:

    def __init__(self, api_key: str, model: str = "qwen3.5-9b"):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://crof.ai/v1"
        )
        self.model = model
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
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=150,
                temperature=0.3,
            )

            msg = response.choices[0].message

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    func_name = tc.function.name
                    func_args = json.loads(tc.function.arguments)
                    handler = self._tool_map.get(func_name)
                    if handler:
                        result = await handler(**func_args)
                        if func_name == "send_telegram_message":
                            from jarvis.config import Config
                            self.client.chat.completions.create(
                                model=self.model,
                                messages=[{"role": "system", "content": (
                                    "Responda em 1 frase confirmando que a mensagem foi enviada. "
                                    "Nao repita o conteudo da mensagem."
                                )}, {"role": "user", "content": user_text}],
                                max_tokens=50,
                                temperature=0.3,
                            )
                            return {
                                "intent": "chat",
                                "response": f"Pronto. Mensagem enviada.",
                                "text": user_text,
                                "source": "crof_ai|tool",
                                "confidence": 0.9,
                                "tool_action": {"type": "send_message", "message": func_args.get("message", "")}
                            }

                messages.append(msg)
                for tc in msg.tool_calls:
                    handler = self._tool_map.get(tc.function.name)
                    if handler:
                        result = await handler(**json.loads(tc.function.arguments))
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result if isinstance(result, str) else json.dumps(result)
                        })

                final = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=100,
                    temperature=0.3,
                )
                response_text = final.choices[0].message.content
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
