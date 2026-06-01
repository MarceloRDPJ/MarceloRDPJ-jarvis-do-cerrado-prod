"""
Jarvis do Cerrado — Web Dashboard API
=====================================
Painel de controle completo estilo Iron Man.
Gerencia: sistema, fan, bot personality, webhooks, MCP, integrações.
"""

import logging
import os
import time
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("api")

# ──────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────
app = FastAPI(title="Jarvis do Cerrado — Control Center")

# ──────────────────────────────────────────────
# Static Files
# ──────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ──────────────────────────────────────────────
# Injected Services (set by main.py)
# ──────────────────────────────────────────────
# app.state.fan_service
# app.state.bot_app
# app.state.personality_service
# app.state.webhook_manager
# app.state.mcp_handler
# app.state.integration_engine
# app.state.automation_service


# ===================================================================
# MODELS
# ===================================================================

class FanConfig(BaseModel):
    mode: str = "auto"  # auto, manual, pwm
    speed_percent: int = 50  # 0-100 (PWM)
    threshold_on: float = 60.0
    threshold_off: float = 50.0
    curve_points: Optional[List[Dict[str, float]]] = None

class PersonalityEntry(BaseModel):
    category: str
    key: str
    responses: List[str]

class WebhookConfig(BaseModel):
    id: Optional[str] = None
    name: str
    url: str
    events: List[str]
    active: bool = True
    secret: Optional[str] = None

class IntegrationConfig(BaseModel):
    id: Optional[str] = None
    name: str
    type: str  # workflow, chatbot, webhook, custom
    config: Dict[str, Any] = {}
    active: bool = True

class BotSettings(BaseModel):
    language: str = "pt-BR"
    tone: str = "casual"  # casual, formal, tech, humorous
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"
    auto_greeting: bool = True
    notification_level: str = "normal"  # minimal, normal, verbose


# ===================================================================
# HELPERS
# ===================================================================

def get_service(name: str):
    """Get an injected service or return None."""
    return getattr(app.state, name, None)

def service_required(name: str):
    """Decorator to check if a service is available."""
    service = get_service(name)
    if not service:
        raise HTTPException(status_code=503, detail=f"Service '{name}' not available")
    return service


# ===================================================================
# ROOT / DASHBOARD
# ===================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        content="<h1>Jarvis Dashboard UI not found</h1><p>Run the build or check static/ directory.</p>",
        status_code=404,
    )


# ===================================================================
# SYSTEM
# ===================================================================

@app.get("/api/system/status")
async def get_system_status():
    """Full system status: CPU, RAM, Disk, Temp, Uptime, Processes."""
    try:
        from jarvis.modules.system import SystemModule
        raw = await SystemModule.get_raw_status()
        return JSONResponse(content=raw)
    except Exception as e:
        logger.error(f"System status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/system/health")
async def get_system_health():
    """Quick health check."""
    from jarvis.core.llm_fallback import LLMFallbackEngine
    local_llm = LLMFallbackEngine()
    return {
        "status": "ok",
        "timestamp": time.time(),
        "local_llm": {
            "backend": local_llm.backend,
            "model": local_llm.model,
            "available": local_llm.is_available(),
        },
    }


@app.post("/api/system/reboot")
async def reboot_system():
    """Reboot the Raspberry Pi."""
    from jarvis.modules.system import SystemModule
    result = SystemModule.reboot_device()
    return {"status": "success", "message": result}


@app.get("/api/system/docker")
async def list_docker_containers():
    """List running Docker containers."""
    from jarvis.modules.system import SystemModule
    result = await SystemModule.list_docker()
    return {"containers": result}


@app.get("/api/system/processes")
async def get_system_processes(limit: int = Query(20, le=100)):
    """List top processes by CPU usage."""
    import psutil
    processes = []
    for proc in sorted(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']),
                       key=lambda p: p.info['cpu_percent'] or 0, reverse=True)[:limit]:
        try:
            processes.append({
                "pid": proc.info['pid'],
                "name": proc.info['name'],
                "cpu": proc.info['cpu_percent'] or 0,
                "memory": proc.info['memory_percent'] or 0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {"processes": processes}


@app.get("/api/system/logs")
async def get_system_logs(lines: int = Query(50, le=200)):
    """Get recent system events from persistence."""
    from jarvis.database.persistence import Persistence
    try:
        events = Persistence.get_recent_snapshots(1440, limit=lines)
        return {"logs": events}
    except Exception as e:
        return {"logs": [], "error": str(e)}


# ===================================================================
# FAN CONTROL (AVANÇADO)
# ===================================================================

@app.get("/api/fan/status")
async def get_fan_status():
    """Get detailed fan status with hardware info."""
    fan_service = get_service("fan_service")
    if not fan_service:
        return JSONResponse(content={
            "available": False,
            "message": "FanControlService not initialized"
        })

    state = "on" if fan_service.fan and fan_service.fan.is_active else "off"
    return JSONResponse(content={
        "available": fan_service.fan is not None,
        "state": state,
        "mode": "pwm" if hasattr(fan_service, 'pwm_mode') and fan_service.pwm_mode else "onoff",
        "speed_percent": getattr(fan_service, 'speed_percent', 100 if state == "on" else 0),
        "manual_override": fan_service.manual_override,
        "threshold_on": fan_service.threshold_on,
        "threshold_off": fan_service.threshold_off,
        "gpio_pin": fan_service.pin,
        "current_temp": None,  # Will be filled
    })


@app.post("/api/fan/toggle")
async def toggle_fan():
    """Toggle fan on/off."""
    fan_service = service_required("fan_service")
    if not fan_service.fan:
        raise HTTPException(status_code=500, detail="Fan hardware unavailable")

    if fan_service.fan.is_active:
        fan_service.fan.off()
        fan_service.manual_override = True
        return {"status": "success", "state": "off", "mode": "manual"}
    else:
        fan_service.fan.on()
        fan_service.manual_override = True
        return {"status": "success", "state": "on", "mode": "manual"}


@app.post("/api/fan/speed")
async def set_fan_speed(config: FanConfig):
    """Set fan speed with PWM support."""
    fan_service = service_required("fan_service")
    if not fan_service.fan:
        raise HTTPException(status_code=500, detail="Fan hardware unavailable")

    speed = max(0, min(100, config.speed_percent))

    if speed == 0:
        fan_service.fan.off()
    else:
        # Try PWM if supported
        try:
            if hasattr(fan_service.fan, 'value'):
                fan_service.fan.value = speed / 100.0
                fan_service.pwm_mode = True
                fan_service.speed_percent = speed
            else:
                fan_service.fan.on()
        except Exception:
            fan_service.fan.on()

    fan_service.manual_override = (config.mode != "auto")
    return {
        "status": "success",
        "speed_percent": speed,
        "mode": config.mode if not fan_service.manual_override else "manual",
        "state": "on" if speed > 0 else "off"
    }


@app.post("/api/fan/config")
async def set_fan_config(config: FanConfig):
    """Configure fan thresholds and curves."""
    fan_service = service_required("fan_service")

    if config.mode == "auto":
        fan_service.manual_override = False
    else:
        fan_service.manual_override = True

    fan_service.threshold_on = config.threshold_on
    fan_service.threshold_off = config.threshold_off

    if config.curve_points:
        fan_service.curve_points = config.curve_points

    return {
        "status": "success",
        "threshold_on": fan_service.threshold_on,
        "threshold_off": fan_service.threshold_off,
        "mode": "auto" if not fan_service.manual_override else "manual",
        "curve_points": getattr(fan_service, 'curve_points', None)
    }


@app.post("/api/fan/auto")
async def set_fan_auto():
    """Return fan to automatic temperature-based control."""
    fan_service = service_required("fan_service")
    fan_service.manual_override = False
    return {"status": "success", "mode": "auto"}


# ===================================================================
# BOT PERSONALITY & CONFIGURATION
# ===================================================================

@app.get("/api/bot/personality")
async def get_personality():
    """Get all personality categories and responses."""
    from jarvis.core.personality import Personality
    categories = {}
    for attr in dir(Personality):
        if attr.isupper() and not attr.startswith('_'):
            val = getattr(Personality, attr)
            if isinstance(val, list):
                categories[attr] = val
            elif isinstance(val, dict):
                categories[attr] = val
    return {"categories": categories}


@app.post("/api/bot/personality")
async def update_personality(entry: PersonalityEntry):
    """Update a personality category or add new responses."""
    from jarvis.core.personality import Personality
    category = entry.category.upper()
    if not hasattr(Personality, category):
        setattr(Personality, category, [])
    
    current = getattr(Personality, category)
    if isinstance(current, list):
        if entry.key == "__replace__":
            setattr(Personality, category, entry.responses)
        else:
            current.extend(entry.responses)
            setattr(Personality, category, current)
    elif isinstance(current, dict):
        current[entry.key] = entry.responses
        setattr(Personality, category, current)
    
    return {"status": "success", "category": category, "count": len(entry.responses)}


@app.get("/api/bot/settings")
async def get_bot_settings():
    """Get current bot settings."""
    from jarvis.config import Config
    return {
        "language": "pt-BR",
        "tone": "casual",
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
        "auto_greeting": True,
        "notification_level": "normal",
        "timezone": Config.TIMEZONE,
        "allowed_user_id": Config.ALLOWED_USER_ID,
        "local_ai_provider": Config.LOCAL_LLM_BACKEND,
        "local_llm_model": Config.LOCAL_LLM_MODEL,
        "intent_confidence": Config.INTENT_CONFIDENCE_THRESHOLD,
    }


@app.post("/api/bot/settings")
async def update_bot_settings(settings: BotSettings):
    """Update bot settings (persisted to persistence layer)."""
    from jarvis.database.persistence import Persistence
    Persistence.set_state("bot_settings", settings.dict())
    return {"status": "success", "settings": settings.dict()}


@app.get("/api/bot/local-brain")
async def get_local_brain():
    """Get all local brain knowledge entries."""
    from jarvis.nlp.local_brain import LocalBrain
    brain = LocalBrain()
    return {"knowledge": brain.static_kb, "count": len(brain.static_kb)}


@app.post("/api/bot/local-brain")
async def add_local_brain_entry(key: str = Body(...), response: str = Body(...)):
    """Add a new entry to the local brain knowledge base."""
    from jarvis.nlp.local_brain import LocalBrain
    brain = LocalBrain()
    brain.static_kb[key.lower().strip()] = [response]
    # Persist the update
    from jarvis.database.persistence import Persistence
    Persistence.set_state("local_brain_custom", brain.static_kb)
    return {"status": "success", "key": key}


@app.get("/api/bot/intents")
async def get_intent_rules():
    """Get all intent mapping rules."""
    from jarvis.nlp.intent_engine import IntentEngine
    engine = IntentEngine()
    return {"intents": engine.intents}


# ===================================================================
# NETWORK
# ===================================================================

@app.get("/api/network/scan")
async def scan_network(depth: str = Query("standard", pattern="^(standard|deep|quick)$")):
    """Scan the local network for devices."""
    from jarvis.modules.network import NetworkModule
    try:
        if depth == "deep":
            devices = await NetworkModule.scan_network_deep()
        else:
            devices = await NetworkModule.scan_network()
        return {"devices": devices, "count": len(devices), "depth": depth}
    except Exception as e:
        logger.error(f"Network scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/network/speedtest")
async def run_speedtest():
    """Run an internet speed test."""
    from jarvis.modules.network import NetworkModule
    result = await NetworkModule.run_speedtest()
    return {"result": result}


@app.get("/api/network/ping")
async def check_ping():
    """Check internet connectivity with ping metrics."""
    from jarvis.modules.network import NetworkModule
    metrics = await NetworkModule.get_ping_metrics()
    return metrics


# ===================================================================
# HYDRATION
# ===================================================================

@app.get("/api/hydration/status")
async def get_hydration_status():
    """Get hydration status for the configured user."""
    from jarvis.config import Config
    from jarvis.modules.hydration import HydrationModule
    chat_id = Config.ALLOWED_USER_ID
    status = HydrationModule.get_status_message(chat_id)
    return {"status": status}


@app.get("/api/hydration/history")
async def get_hydration_history(days: int = Query(30, le=90)):
    """Get hydration history for the last N days."""
    from jarvis.config import Config
    from jarvis.database.persistence import Persistence
    chat_id = Config.ALLOWED_USER_ID
    history = Persistence.get_hydration_history(chat_id, days)
    return {"history": history, "days": days, "count": len(history)}


# ===================================================================
# WEBHOOKS
# ===================================================================

@app.get("/api/webhooks")
async def list_webhooks():
    """List all registered webhooks."""
    wm = get_service("webhook_manager")
    if not wm:
        return {"webhooks": []}
    return {"webhooks": wm.list_webhooks()}


@app.post("/api/webhooks")
async def create_webhook(config: WebhookConfig):
    """Register a new webhook."""
    wm = service_required("webhook_manager")
    webhook = wm.register_webhook(config.dict())
    return {"status": "success", "webhook": webhook}


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """Remove a webhook."""
    wm = service_required("webhook_manager")
    wm.unregister_webhook(webhook_id)
    return {"status": "success", "deleted": webhook_id}


@app.post("/api/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str):
    """Send a test event to a webhook."""
    wm = service_required("webhook_manager")
    result = await wm.test_webhook(webhook_id)
    return {"status": "success" if result else "failed", "result": result}


@app.get("/api/webhooks/logs")
async def get_webhook_logs(limit: int = Query(50, le=200)):
    """Get recent webhook execution logs."""
    wm = service_required("webhook_manager")
    return {"logs": wm.get_logs(limit)}


# ===================================================================
# MCP — MODEL CONTEXT PROTOCOL
# ===================================================================

@app.get("/api/mcp/tools")
async def list_mcp_tools():
    """List available MCP tools."""
    mcp = get_service("mcp_handler")
    if not mcp:
        # Return built-in tools even without MCP handler
        return {
            "tools": [
                {"name": "system_status", "description": "Get system status", "parameters": {}},
                {"name": "network_scan", "description": "Scan network devices", "parameters": {"depth": {"type": "string"}}},
                {"name": "fan_control", "description": "Control fan", "parameters": {"action": {"type": "string"}, "speed": {"type": "integer"}}},
                {"name": "send_notification", "description": "Send Telegram notification", "parameters": {"message": {"type": "string"}}},
                {"name": "run_speedtest", "description": "Run internet speed test", "parameters": {}},
                {"name": "block_site", "description": "Block a website via AdGuard", "parameters": {"domain": {"type": "string"}}},
                {"name": "get_hydration", "description": "Get hydration status", "parameters": {}},
                {"name": "list_reminders", "description": "List active reminders", "parameters": {}},
            ]
        }
    return {"tools": mcp.list_tools()}


@app.post("/api/mcp/execute")
async def execute_mcp_tool(request: Request):
    """Execute an MCP tool."""
    body = await request.json()
    tool_name = body.get("tool")
    parameters = body.get("parameters", {})

    mcp = get_service("mcp_handler")
    if mcp:
        result = await mcp.execute_tool(tool_name, parameters)
        return {"result": result}

    # Built-in execution for common tools
    from jarvis.modules.system import SystemModule
    from jarvis.modules.network import NetworkModule

    if tool_name == "system_status":
        raw = await SystemModule.get_raw_status()
        return {"result": raw}
    elif tool_name == "network_scan":
        devices = await NetworkModule.scan_network()
        return {"result": {"devices": devices}}
    elif tool_name == "run_speedtest":
        result = await NetworkModule.run_speedtest()
        return {"result": result}
    elif tool_name == "send_notification":
        bot = getattr(app.state, "bot_app", None)
        if bot:
            from jarvis.config import Config
            await bot.bot.send_message(chat_id=Config.ALLOWED_USER_ID, text=parameters.get("message", ""))
            return {"result": "Notification sent"}
        return {"result": "Bot not available"}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")


@app.get("/api/mcp/resources")
async def list_mcp_resources():
    """List available MCP resources (data endpoints)."""
    return {
        "resources": [
            {"uri": "jarvis://system/status", "description": "Real-time system status"},
            {"uri": "jarvis://network/devices", "description": "Connected network devices"},
            {"uri": "jarvis://network/stats", "description": "Network statistics from AdGuard"},
            {"uri": "jarvis://hydration/today", "description": "Today's hydration data"},
            {"uri": "jarvis://bot/personality", "description": "Bot personality configuration"},
            {"uri": "jarvis://system/logs", "description": "Recent system logs"},
        ]
    }


# ===================================================================
# INTEGRATIONS (n8n-like, Typebot-like)
# ===================================================================

@app.get("/api/integrations")
async def list_integrations():
    """List all registered integrations."""
    engine = get_service("integration_engine")
    if not engine:
        return {"integrations": []}
    return {"integrations": engine.list_integrations()}


@app.post("/api/integrations")
async def create_integration(config: IntegrationConfig):
    """Register a new integration."""
    engine = service_required("integration_engine")
    integration = engine.register_integration(config.dict())
    return {"status": "success", "integration": integration}


@app.delete("/api/integrations/{integration_id}")
async def delete_integration(integration_id: str):
    """Remove an integration."""
    engine = service_required("integration_engine")
    engine.unregister_integration(integration_id)
    return {"status": "success"}


@app.post("/api/integrations/test")
async def test_integration(request: Request):
    """Test an integration configuration."""
    body = await request.json()
    return {"status": "success", "message": "Integration test completed", "data": body}


@app.get("/api/integrations/templates")
async def list_integration_templates():
    """List available pre-built integration templates."""
    return {
        "templates": [
            {
                "id": "night_mode",
                "name": "Modo Noturno Automático",
                "description": "Silencia notificações e ativa modo escuro às 22h",
                "type": "workflow",
                "steps": [
                    {"type": "schedule", "config": {"time": "22:00"}},
                    {"type": "action", "config": {"action": "quiet_hours_on"}},
                    {"type": "notification", "config": {"message": "🌙 Modo noturno ativado"}}
                ]
            },
            {
                "id": "hydration_reminder",
                "name": "Lembrete de Hidratação",
                "description": "Lembra de beber água a cada 2 horas",
                "type": "workflow",
                "steps": [
                    {"type": "schedule", "config": {"interval": 120}},
                    {"type": "notification", "config": {"message": "💧 Hora de beber água!"}}
                ]
            },
            {
                "id": "welcome_message",
                "name": "Mensagem de Boas-Vindas",
                "description": "Envia mensagem personalizada ao detectar novo dispositivo",
                "type": "chatbot",
                "steps": [
                    {"type": "trigger", "config": {"event": "network.new_device"}},
                    {"type": "action", "config": {"action": "send_message", "message": "🆕 Novo dispositivo detectado na rede!"}}
                ]
            },
            {
                "id": "internet_alert",
                "name": "Alerta de Internet",
                "description": "Notifica quando a internet cai ou volta",
                "type": "workflow",
                "steps": [
                    {"type": "trigger", "config": {"event": "network.status_changed"}},
                    {"type": "condition", "config": {"field": "status", "operator": "eq", "value": "down"}},
                    {"type": "notification", "config": {"message": "🚨 Internet caiu!"}}
                ]
            }
        ]
    }


# ===================================================================
# AUTOMATIONS
# ===================================================================

@app.get("/api/automations")
async def list_automations():
    """List all registered automations."""
    automation = get_service("automation_service")
    if not automation:
        return {"automations": []}
    return {"automations": automation.rules}


@app.post("/api/automations/{rule_id}/toggle")
async def toggle_automation(rule_id: str):
    """Enable/disable an automation rule."""
    automation = service_required("automation_service")
    for rule in automation.rules:
        if rule["id"] == rule_id:
            rule["enabled"] = not rule["enabled"]
            return {"status": "success", "rule_id": rule_id, "enabled": rule["enabled"]}
    raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")


# ===================================================================
# DASHBOARD DATA (Batch endpoint for Dashboard home)
# ===================================================================

@app.get("/api/dashboard")
async def get_dashboard_data():
    """Get all essential dashboard data in one call."""
    from jarvis.modules.system import SystemModule
    from jarvis.config import Config

    data = {"timestamp": time.time()}

    # System
    try:
        data["system"] = await SystemModule.get_raw_status()
    except Exception as e:
        data["system"] = {"error": str(e)}

    # Fan
    fan_service = get_service("fan_service")
    if fan_service and fan_service.fan:
        data["fan"] = {
            "available": True,
            "state": "on" if fan_service.fan.is_active else "off",
            "manual_override": fan_service.manual_override,
            "threshold_on": fan_service.threshold_on,
            "threshold_off": fan_service.threshold_off,
        }
    else:
        data["fan"] = {"available": False}

    # Network (quick)
    try:
        from jarvis.modules.network import NetworkModule
        metrics = await NetworkModule.get_ping_metrics()
        data["internet"] = metrics
    except Exception:
        data["internet"] = {"success": False}

    # Bot Info
    data["bot"] = {
        "timezone": Config.TIMEZONE,
        "local_ai_provider": Config.LOCAL_LLM_BACKEND,
        "local_llm_model": Config.LOCAL_LLM_MODEL,
        "local_llm_available": False,
        "user_id": Config.ALLOWED_USER_ID,
    }
    try:
        from jarvis.core.llm_fallback import LLMFallbackEngine
        data["bot"]["local_llm_available"] = LLMFallbackEngine().is_available()
    except Exception:
        pass

    return JSONResponse(content=data)


# ===================================================================
# CONFIG / SETTINGS
# ===================================================================

@app.get("/api/config")
async def get_config():
    """Get current configuration (sanitized - no secrets)."""
    from jarvis.config import Config
    return {
        "timezone": Config.TIMEZONE,
        "local_ai_provider": Config.LOCAL_LLM_BACKEND,
        "local_llm_url": Config.LOCAL_LLM_URL,
        "local_llm_model": Config.LOCAL_LLM_MODEL,
        "local_llm_cli_path": Config.LOCAL_LLM_CLI_PATH,
        "local_llm_model_path": Config.LOCAL_LLM_MODEL_PATH,
        "local_llm_context_tokens": Config.LOCAL_LLM_CONTEXT_TOKENS,
        "local_llm_threads": Config.LOCAL_LLM_THREADS,
        "local_llm_timeout_seconds": Config.LOCAL_LLM_TIMEOUT_SECONDS,
        "local_llm_max_tokens": Config.LOCAL_LLM_MAX_TOKENS,
        "intent_confidence": Config.INTENT_CONFIDENCE_THRESHOLD,
        "scheduler_interval": Config.SCHEDULER_INTERVAL_SECONDS,
        "hydration_interval": Config.HYDRATION_MIN_INTERVAL_MINUTES,
        "fan_gpio_pin": Config.FAN_GPIO_PIN,
        "fan_temp_on": Config.FAN_TEMP_ON,
        "fan_temp_off": Config.FAN_TEMP_OFF,
        "pc_mac": Config.PC_MAC[:8] + ":***" if Config.PC_MAC else None,
        "pc_ip": os.getenv("PC_IP", "192.168.0.100"),
        "yaml_config": Config.YAML_CONFIG,
    }


# ===================================================================
# EVENTS / REAL-TIME
# ===================================================================

@app.get("/api/events/recent")
async def get_recent_events(limit: int = Query(20, le=100)):
    """Get recent system events."""
    from jarvis.database.persistence import Persistence
    try:
        snapshots = Persistence.get_recent_snapshots(60, limit=limit)
        return {"events": snapshots}
    except Exception as e:
        return {"events": [], "error": str(e)}


# ===================================================================
# ERROR HANDLING
# ===================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__}
    )
