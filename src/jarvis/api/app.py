import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os

from jarvis.modules.system import SystemModule
from jarvis.modules.network import NetworkModule
from jarvis.config import Config

logger = logging.getLogger("api")

app = FastAPI(title="Jarvis Dashboard API")

# Serve static files for the frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Jarvis Dashboard UI not found</h1>", status_code=404)

@app.get("/api/system/status")
async def get_system_status():
    try:
        raw_status = await SystemModule.get_raw_status()
        return JSONResponse(content=raw_status)
    except Exception as e:
        logger.error(f"Erro ao obter status do sistema: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/api/network/scan")
async def scan_network():
    try:
        # Using the deep scan for detailed dashboard info
        devices = await NetworkModule.scan_network_deep()
        return JSONResponse(content={"devices": devices})
    except Exception as e:
        logger.error(f"Erro ao escanear rede: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/api/fan/toggle")
async def toggle_fan():
    # Retrieve the fan_service instance from the app lifecycle if possible.
    fan_service = getattr(app.state, "fan_service", None)

    if not fan_service or not fan_service.fan:
        raise HTTPException(status_code=500, detail="FanControlService unavailable")

    if fan_service.fan.is_active:
        fan_service.fan.off()
        fan_service.manual_override = True
        # Reset override after 1 hour (or until next manual toggle)
        # Ideally this would be a task, but for a simple fix setting the flag is enough
        return {"status": "success", "state": "off"}
    else:
        fan_service.fan.on()
        fan_service.manual_override = True
        return {"status": "success", "state": "on"}

@app.post("/api/fan/auto")
async def auto_fan():
    fan_service = getattr(app.state, "fan_service", None)
    if not fan_service or not fan_service.fan:
        raise HTTPException(status_code=500, detail="FanControlService unavailable")

    fan_service.manual_override = False
    return {"status": "success", "state": "auto"}

@app.get("/api/fan/status")
async def get_fan_status():
    fan_service = getattr(app.state, "fan_service", None)

    if not fan_service:
        return JSONResponse(content={"available": False})

    state = "on" if fan_service.fan and fan_service.fan.is_active else "off"
    return JSONResponse(content={
        "available": fan_service.fan is not None,
        "state": state,
        "threshold_on": fan_service.threshold_on,
        "threshold_off": fan_service.threshold_off
    })
