"""
Webhook Manager — Jarvis do Cerrado
====================================
Gerencia webhooks de entrada e saída para integração com serviços externos.
"""

import logging
import json
import hashlib
import hmac
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import aiohttp

logger = logging.getLogger("api.webhooks")


class WebhookManager:
    """
    Sistema de Webhooks do Jarvis.
    
    - Webhooks de saída: notificam serviços externos sobre eventos
    - Webhooks de entrada: recebem comandos de serviços externos
    - Fila de execução com logs
    """

    def __init__(self, app_state=None):
        self.app = app_state
        self.webhooks: Dict[str, Dict[str, Any]] = {}
        self.execution_logs: List[Dict[str, Any]] = []
        self._load_webhooks()

    def _load_webhooks(self):
        """Load persisted webhooks."""
        try:
            from jarvis.database.persistence import Persistence
            saved = Persistence.get_state("webhooks", [])
            for wh in saved:
                self.webhooks[wh["id"]] = wh
            logger.info(f"Loaded {len(self.webhooks)} webhooks")
        except Exception as e:
            logger.warning(f"Could not load webhooks: {e}")

    def _save_webhooks(self):
        """Persist webhooks to database."""
        try:
            from jarvis.database.persistence import Persistence
            Persistence.set_state("webhooks", list(self.webhooks.values()))
        except Exception as e:
            logger.error(f"Failed to save webhooks: {e}")

    def register_webhook(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new webhook endpoint."""
        webhook_id = config.get("id", str(uuid.uuid4()))
        webhook = {
            "id": webhook_id,
            "name": config.get("name", "Unnamed Webhook"),
            "url": config["url"],
            "events": config.get("events", ["*"]),
            "active": config.get("active", True),
            "secret": config.get("secret", ""),
            "created_at": datetime.now().isoformat(),
            "last_call": None,
            "success_count": 0,
            "fail_count": 0,
        }
        self.webhooks[webhook_id] = webhook
        self._save_webhooks()
        logger.info(f"Webhook registered: {webhook['name']} ({webhook_id})")
        return webhook

    def unregister_webhook(self, webhook_id: str):
        """Remove a webhook."""
        if webhook_id in self.webhooks:
            wh = self.webhooks.pop(webhook_id)
            self._save_webhooks()
            logger.info(f"Webhook removed: {wh['name']} ({webhook_id})")

    def list_webhooks(self) -> List[Dict[str, Any]]:
        """List all registered webhooks."""
        return list(self.webhooks.values())

    def get_webhook(self, webhook_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific webhook."""
        return self.webhooks.get(webhook_id)

    async def dispatch(self, event_type: str, payload: Dict[str, Any]):
        """
        Dispatch an event to all registered webhooks that listen for it.
        Called internally by the system when events occur.
        """
        for wh_id, wh in self.webhooks.items():
            if not wh["active"]:
                continue
            if "*" not in wh["events"] and event_type not in wh["events"]:
                continue

            try:
                await self._send_webhook(wh, event_type, payload)
            except Exception as e:
                logger.error(f"Webhook dispatch error ({wh['name']}): {e}")

    async def _send_webhook(self, webhook: Dict[str, Any], event_type: str, payload: Dict[str, Any]):
        """Send a single webhook request."""
        body = {
            "event": event_type,
            "timestamp": datetime.now().isoformat(),
            "source": "jarvis-do-cerrado",
            "payload": payload,
        }

        headers = {
            "Content-Type": "application/json",
            "X-Jarvis-Event": event_type,
            "X-Jarvis-Timestamp": str(int(time.time())),
        }

        # Sign the request if secret is configured
        if webhook.get("secret"):
            signature = hmac.new(
                webhook["secret"].encode(),
                json.dumps(body).encode(),
                hashlib.sha256
            ).hexdigest()
            headers["X-Jarvis-Signature"] = signature

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook["url"],
                    json=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    status = response.status
                    body_text = await response.text()
        except Exception as e:
            status = 0
            body_text = str(e)

        log_entry = {
            "webhook_id": webhook["id"],
            "webhook_name": webhook["name"],
            "event": event_type,
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "success": 200 <= status < 300,
            "response": body_text[:500],
        }
        self.execution_logs.append(log_entry)

        # Trim logs to keep last 1000
        if len(self.execution_logs) > 1000:
            self.execution_logs = self.execution_logs[-1000:]

        if 200 <= status < 300:
            webhook["last_call"] = "success"
            webhook["success_count"] += 1
        else:
            webhook["last_call"] = "failed"
            webhook["fail_count"] += 1

        self._save_webhooks()

    async def test_webhook(self, webhook_id: str) -> bool:
        """Send a test event to a webhook."""
        wh = self.webhooks.get(webhook_id)
        if not wh:
            return False
        try:
            await self._send_webhook(wh, "test", {"message": "This is a test event from Jarvis do Cerrado"})
            return True
        except Exception:
            return False

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent webhook execution logs."""
        return list(reversed(self.execution_logs[-limit:]))

    async def handle_incoming(self, request_body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Handle an incoming webhook request from an external service.
        Processes commands and returns a response.
        """
        event = request_body.get("event", "unknown")
        payload = request_body.get("payload", {})

        logger.info(f"Incoming webhook: {event}")

        # Process known commands
        if event == "command":
            command = payload.get("command", "")
            params = payload.get("parameters", {})

            # Process the command via the bot's executor if available
            bot_app = getattr(self.app, "bot_app", None) if self.app else None
            if bot_app:
                executor = bot_app.bot_data.get("executor")
                if executor:
                    from jarvis.core import router
                    intent = await router.route(command, 0)
                    response = await executor.execute(intent, 0)
                    return {
                        "status": "executed",
                        "event": event,
                        "response": response,
                    }

            return {
                "status": "received",
                "event": event,
                "message": f"Command '{command}' received (executor not available)",
            }

        elif event == "ping":
            return {
                "status": "pong",
                "timestamp": datetime.now().isoformat(),
                "version": "2.0.0",
            }

        elif event == "status":
            from jarvis.modules.system import SystemModule
            status = await SystemModule.get_raw_status()
            return {
                "status": "ok",
                "data": status,
            }

        else:
            return {
                "status": "received",
                "event": event,
                "message": f"Event '{event}' received",
            }
