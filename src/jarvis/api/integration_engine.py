"""
Integration Engine — Jarvis do Cerrado
=======================================
Motor local simples para workflows e chatbots básicos.

Não é substituto completo de n8n/Typebot; valida configurações para evitar
salvar fluxos que parecem ativos mas não executam.
"""

import logging
import uuid
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("api.integrations")


class IntegrationEngine:
    """
    Motor de Integrações do Jarvis.
    
    Suporta workflows e chatbots básicos com validação explícita.
    """

    def __init__(self, app_state):
        self.app = app_state
        self.integrations: Dict[str, Dict[str, Any]] = {}
        self.workflow_scheduler: Optional[asyncio.Task] = None
        self._load_integrations()

    def _load_integrations(self):
        """Load persisted integrations."""
        try:
            from jarvis.database.persistence import Persistence
            saved = Persistence.get_state("integrations", [])
            for integration in saved:
                self.integrations[integration["id"]] = integration
            logger.info(f"Loaded {len(self.integrations)} integrations")
        except Exception as e:
            logger.warning(f"Could not load integrations: {e}")

    def _save_integrations(self):
        """Persist integrations to database."""
        try:
            from jarvis.database.persistence import Persistence
            Persistence.set_state("integrations", list(self.integrations.values()))
        except Exception as e:
            logger.error(f"Failed to save integrations: {e}")

    def register_integration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new integration."""
        errors = self.validate_config(config)
        if errors:
            raise ValueError("; ".join(errors))

        integration_id = config.get("id", str(uuid.uuid4()))
        
        integration = {
            "id": integration_id,
            "name": config.get("name", "Unnamed Integration"),
            "type": config.get("type", "custom"),
            "config": config.get("config", {}),
            "active": config.get("active", True),
            "created_at": datetime.now().isoformat(),
            "last_run": None,
            "run_count": 0,
        }

        # Validate based on type
        if integration["type"] == "workflow":
            integration["config"]["steps"] = config.get("config", {}).get("steps", [])
        elif integration["type"] == "chatbot":
            integration["config"]["flows"] = config.get("config", {}).get("flows", [])
        elif integration["type"] == "webhook":
            integration["config"]["endpoint"] = config.get("config", {}).get("endpoint", "/integration/incoming")

        self.integrations[integration_id] = integration
        self._save_integrations()

        # Start workflow scheduler if needed
        if integration["type"] == "workflow" and integration["active"]:
            self._ensure_scheduler()

        logger.info(f"Integration registered: {integration['name']} ({integration_id}) [{integration['type']}]")
        return integration

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Return validation errors for configs that cannot execute."""
        errors = []
        integration_type = config.get("type", "custom")
        cfg = config.get("config") or {}

        if integration_type == "workflow":
            steps = cfg.get("steps")
            if not isinstance(steps, list) or not steps:
                return ["workflow precisa de config.steps com ao menos um step"]
            supported = {"schedule", "notification", "action", "condition", "trigger"}
            for index, step in enumerate(steps):
                step_type = step.get("type")
                step_config = step.get("config") or {}
                if step_type not in supported:
                    errors.append(f"step {index}: tipo '{step_type}' não suportado")
                    continue
                if step_type == "schedule" and not (step_config.get("time") or step_config.get("interval")):
                    errors.append(f"step {index}: schedule precisa de time ou interval")
                elif step_type == "notification" and not step_config.get("message"):
                    errors.append(f"step {index}: notification precisa de message")
                elif step_type == "action" and not step_config.get("action"):
                    errors.append(f"step {index}: action precisa de action")
                elif step_type == "condition" and not step_config.get("field"):
                    errors.append(f"step {index}: condition precisa de field")
                elif step_type == "trigger" and not step_config.get("event"):
                    errors.append(f"step {index}: trigger precisa de event")

        elif integration_type == "chatbot":
            flows = cfg.get("flows")
            if not isinstance(flows, list) or not flows:
                return ["chatbot precisa de config.flows com ao menos um fluxo"]
            for index, flow in enumerate(flows):
                if not flow.get("trigger"):
                    errors.append(f"flow {index}: trigger obrigatório")
                responses = flow.get("responses")
                actions = flow.get("actions")
                fallback = flow.get("fallback")
                if not responses and not actions and not fallback:
                    errors.append(f"flow {index}: informe responses, actions ou fallback")
                if responses is not None and not isinstance(responses, list):
                    errors.append(f"flow {index}: responses deve ser lista")

        elif integration_type == "webhook":
            if not cfg.get("endpoint"):
                errors.append("webhook precisa de config.endpoint")

        else:
            errors.append(f"tipo de integração '{integration_type}' não suportado")

        return errors

    def unregister_integration(self, integration_id: str):
        """Remove an integration."""
        if integration_id in self.integrations:
            integration = self.integrations.pop(integration_id)
            self._save_integrations()
            logger.info(f"Integration removed: {integration['name']} ({integration_id})")

    def list_integrations(self) -> List[Dict[str, Any]]:
        """List all registered integrations."""
        return list(self.integrations.values())

    def get_integration(self, integration_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific integration."""
        return self.integrations.get(integration_id)

    def _ensure_scheduler(self):
        """Ensure the workflow scheduler is running."""
        if not self.workflow_scheduler or self.workflow_scheduler.done():
            self.workflow_scheduler = asyncio.create_task(self._scheduler_loop())
            logger.info("Workflow scheduler started")

    async def _scheduler_loop(self):
        """Background loop that checks and executes scheduled workflows."""
        while True:
            try:
                for integration in self.integrations.values():
                    if not integration["active"] or integration["type"] != "workflow":
                        continue

                    config = integration["config"]
                    for step in config.get("steps", []):
                        if step.get("type") == "schedule":
                            await self._handle_schedule_step(integration, step)

                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Workflow scheduler error: {e}")
                await asyncio.sleep(60)

    async def _handle_schedule_step(self, integration: Dict[str, Any], step: Dict[str, Any]):
        """Handle a schedule-type workflow step."""
        from jarvis.database.persistence import Persistence
        from jarvis.config import Config
        from datetime import datetime
        
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        step_config = step.get("config", {})
        scheduled_time = step_config.get("time")
        interval = step_config.get("interval")  # minutes
        
        if scheduled_time and scheduled_time == current_time:
            # Check if we already ran this step recently
            last_run_key = f"workflow_last_run_{integration['id']}"
            last_run = Persistence.get_state(last_run_key)
            
            if last_run != now.strftime("%Y-%m-%d"):
                Persistence.set_state(last_run_key, now.strftime("%Y-%m-%d"))
                await self._execute_workflow_steps(integration, step)
        
        elif interval:
            last_run_key = f"workflow_last_run_{integration['id']}"
            last_run = Persistence.get_state(last_run_key)
            
            if last_run:
                last_dt = datetime.fromisoformat(last_run)
                elapsed = (now - last_dt).total_seconds() / 60
                if elapsed >= interval:
                    Persistence.set_state(last_run_key, now.isoformat())
                    await self._execute_workflow_steps(integration, step)
            else:
                Persistence.set_state(last_run_key, now.isoformat())

    async def _execute_workflow_steps(self, integration: Dict[str, Any], trigger_step: Dict[str, Any]):
        """Execute all steps in a workflow after being triggered."""
        config = integration["config"]
        steps = config.get("steps", [])
        
        # Find steps after the trigger
        trigger_idx = -1
        for i, s in enumerate(steps):
            if s is trigger_step:
                trigger_idx = i
                break
        
        action_steps = steps[trigger_idx + 1:] if trigger_idx >= 0 else steps
        
        for step in action_steps:
            try:
                await self._execute_step(step, {})
            except Exception as e:
                logger.error(f"Workflow step error: {e}")
        
        # Update run count
        integration["run_count"] += 1
        integration["last_run"] = datetime.now().isoformat()
        self._save_integrations()

    async def _execute_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single workflow step."""
        step_type = step.get("type", "")
        config = step.get("config", {})
        from jarvis.config import Config

        if step_type == "notification":
            bot = getattr(self.app, "bot_app", None)
            if bot and Config.ALLOWED_USER_ID:
                message = config.get("message", "🤖 Integration notification")
                await bot.bot.send_message(chat_id=Config.ALLOWED_USER_ID, text=message)
                return {"sent": True}

        elif step_type == "action":
            action = config.get("action", "")
            if action == "quiet_hours_on":
                from jarvis.database.persistence import Persistence
                Persistence.set_state("quiet_hours_active", True)
            elif action == "quiet_hours_off":
                from jarvis.database.persistence import Persistence
                Persistence.set_state("quiet_hours_active", False)
            elif action == "send_message":
                message = config.get("message", "")
                bot = getattr(self.app, "bot_app", None)
                if bot and Config.ALLOWED_USER_ID:
                    await bot.bot.send_message(chat_id=Config.ALLOWED_USER_ID, text=message)

        elif step_type == "condition":
            field = config.get("field", "")
            operator = config.get("operator", "eq")
            value = config.get("value", "")
            
            # Simple condition evaluation
            actual = context.get(field)
            if operator == "eq" and actual == value:
                return {"condition": True}
            elif operator == "ne" and actual != value:
                return {"condition": True}
            elif operator == "gt" and actual is not None and actual > value:
                return {"condition": True}
            
            return {"condition": False}

        elif step_type == "trigger":
            event = config.get("event", "")
            # Triggers wait for events, handled by _handle_event
            logger.info(f"Trigger step registered for event: {event}")

        return {"status": "executed"}

    async def handle_event(self, event_type: str, payload: Dict[str, Any]):
        """
        Handle a system event and trigger matching integrations.
        Called by the system when events occur.
        """
        for integration in self.integrations.values():
            if not integration["active"]:
                continue

            config = integration["config"]
            steps = config.get("steps", [])
            
            for step in steps:
                if step.get("type") == "trigger":
                    trigger_config = step.get("config", {})
                    if trigger_config.get("event") == event_type:
                        logger.info(f"Integration '{integration['name']}' triggered by {event_type}")
                        await self._execute_workflow_steps(integration, step)

    async def handle_chatbot_message(self, message: str, chat_id: int) -> Optional[str]:
        """
        Process a message through chatbot-type integrations.
        Simulates Typebot-like flow processing.
        """
        for integration in self.integrations.values():
            if not integration["active"] or integration["type"] != "chatbot":
                continue

            config = integration["config"]
            flows = config.get("flows", [])
            
            for flow in flows:
                trigger = flow.get("trigger", "").lower()
                if trigger and trigger in message.lower():
                    responses = flow.get("responses", [])
                    if responses:
                        import random
                        return random.choice(responses)
                    
                    actions = flow.get("actions", [])
                    for action in actions:
                        await self._execute_step(action, {"message": message, "chat_id": chat_id})
                    
                    return flow.get("fallback", "🤖 Comando recebido pela integração!")

        return None

    def get_workflow_templates(self) -> List[Dict[str, Any]]:
        """Get pre-built workflow templates."""
        return [
            {
                "id": "night_mode",
                "name": "🌙 Modo Noturno Automático",
                "description": "Silencia notificações às 22h e reativa às 8h",
                "config": {
                    "steps": [
                        {"type": "schedule", "config": {"time": "22:00"}},
                        {"type": "action", "config": {"action": "quiet_hours_on"}},
                        {"type": "notification", "config": {"message": "🌙 Modo noturno ativado. Lembretes silenciados."}},
                        {"type": "schedule", "config": {"time": "08:00"}},
                        {"type": "action", "config": {"action": "quiet_hours_off"}},
                        {"type": "notification", "config": {"message": "☀️ Bom dia! Modo noturno desativado."}},
                    ]
                }
            },
            {
                "id": "hydration_cheer",
                "name": "💧 Torcida da Hidratação",
                "description": "Envia mensagens de incentivo ao longo do dia",
                "config": {
                    "steps": [
                        {"type": "schedule", "config": {"interval": 120}},
                        {"type": "notification", "config": {"message": "💧 Já bebeu água hoje? Seu copo te espera!"}},
                    ]
                }
            },
            {
                "id": "device_alert",
                "name": "🆕 Alerta de Dispositivo Novo",
                "description": "Notifica quando um dispositivo desconhecido aparece na rede",
                "config": {
                    "steps": [
                        {"type": "trigger", "config": {"event": "network.new_device"}},
                        {"type": "notification", "config": {"message": "🆕 Novo dispositivo detectado na rede!"}},
                    ]
                }
            },
            {
                "id": "internet_monitor",
                "name": "🌐 Monitor de Internet",
                "description": "Avisa quando a internet cai e quando volta",
                "config": {
                    "steps": [
                        {"type": "trigger", "config": {"event": "network.status_changed"}},
                        {"type": "condition", "config": {"field": "status", "operator": "eq", "value": "down"}},
                        {"type": "notification", "config": {"message": "🚨 ALERTA: Internet caiu!"}},
                    ]
                }
            },
        ]

    def get_chatbot_templates(self) -> List[Dict[str, Any]]:
        """Get pre-built chatbot flow templates."""
        return [
            {
                "id": "welcome_bot",
                "name": "👋 Assistente de Boas-Vindas",
                "description": "Responde a saudações com mensagens personalizadas",
                "config": {
                    "flows": [
                        {
                            "trigger": "bom dia",
                            "responses": ["☀️ Bom dia! Que seu dia seja produtivo!", "Bom dia! Já tomou café?"],
                        },
                        {
                            "trigger": "boa tarde",
                            "responses": ["🌤️ Boa tarde! Como está o dia?", "Boa tarde! Precisando de algo?"],
                        },
                        {
                            "trigger": "boa noite",
                            "responses": ["🌙 Boa noite! Descanse bem.", "Boa noite! O sistema continua de olho."],
                        }
                    ]
                }
            },
            {
                "id": "motivation_bot",
                "name": "💪 Bot Motivacional",
                "description": "Envia mensagens motivacionais em momentos específicos",
                "config": {
                    "flows": [
                        {
                            "trigger": "cansado",
                            "responses": ["Respira fundo. Você está indo bem!", "Que tal uma pausa de 5 minutos?"],
                        },
                        {
                            "trigger": "estresse",
                            "responses": ["Calma. Um passo de cada vez.", "Respira. O controle está com você."],
                        }
                    ]
                }
            },
        ]
