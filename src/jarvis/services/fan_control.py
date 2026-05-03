"""
FanControlService — Jarvis do Cerrado
======================================
Controle avançado de ventoinha com suporte PWM para Raspberry Pi.

Modos:
- ON/OFF (digital): Liga/desliga via GPIO
- PWM (analógico): Controle de velocidade via PWM por software
- Auto: Controle automático baseado em temperatura
"""

import asyncio
import logging
from typing import List, Dict, Optional
from jarvis.modules.system import SystemModule
logger = logging.getLogger("services.fan_control")


class FanControlService:
    """
    Serviço para controle da ventoinha do Raspberry Pi.

    Features:
    - Controle PWM (velocidade variável 0-100%)
    - Curvas de temperatura customizáveis
    - Manual override com timeout automático
    - Fallback para ON/OFF quando PWM não disponível
    """

    def __init__(
        self,
        pin: int = 14,
        threshold_on: float = 60.0,
        threshold_off: float = 50.0,
        interval_seconds: int = 10,
    ):
        self.pin = pin
        self.threshold_on = threshold_on
        self.threshold_off = threshold_off
        self.interval = interval_seconds
        self.running = False
        self.fan = None
        self.manual_override = False
        self.pwm_mode = False
        self.speed_percent = 100  # 0-100 for PWM
        self.curve_points: List[Dict[str, float]] = [
            {"temp": 45, "speed": 0},
            {"temp": 55, "speed": 30},
            {"temp": 60, "speed": 60},
            {"temp": 65, "speed": 80},
            {"temp": 70, "speed": 100},
        ]
        self._last_override_time = 0
        self._override_timeout = 3600  # 1 hour
        self._init_gpio()

    def _init_gpio(self):
        """Initialize GPIO with PWM support if available."""
        try:
            # Try PWM first (PiGPIO or software PWM)
            try:
                from gpiozero import PWMOutputDevice
                self.fan = PWMOutputDevice(self.pin, frequency=100)
                self.pwm_mode = True
                self.fan.value = 0  # Start with fan off
                logger.info(f"FanControlService PWM inicializado no GPIO {self.pin} (100Hz)")
            except ImportError:
                # Fallback to digital ON/OFF
                from gpiozero import OutputDevice
                self.fan = OutputDevice(self.pin)
                self.pwm_mode = False
                logger.info(f"FanControlService digital inicializado no GPIO {self.pin}")
        except Exception as e:
            logger.error(f"Erro ao inicializar gpiozero: {e}. Fan em modo simulado.")
            self.fan = None

    async def start(self):
        """Start the fan control service main loop."""
        if self.running:
            return
        self.running = True
        logger.info("🌬️ FanControlService iniciado.")

        while self.running:
            if self.fan is not None:
                try:
                    await self._check_temperature()
                    self._check_override_timeout()
                except Exception as e:
                    logger.error(f"Erro no loop do FanControlService: {e}")
            await asyncio.sleep(self.interval)

    async def _check_temperature(self):
        """Check temperature and adjust fan speed automatically."""
        if self.manual_override:
            return

        raw_status = await SystemModule.get_raw_status()
        temp = raw_status.get("temperature_c")

        if temp is None:
            return

        if self.pwm_mode:
            # Use temperature curve for PWM speed
            speed = self._calculate_curve_speed(temp)

            if speed != self.speed_percent:
                self.speed_percent = speed
                self.fan.value = speed / 100.0
                if speed > 0:
                    logger.debug(f"Temperatura {temp}°C → PWM {speed}%")
        else:
            # Digital ON/OFF mode
            if temp >= self.threshold_on and not self.fan.is_active:
                logger.info(f"Temperatura {temp}°C >= {self.threshold_on}°C. Ligando ventoinha.")
                self.fan.on()
            elif temp <= self.threshold_off and self.fan.is_active:
                logger.info(f"Temperatura {temp}°C <= {self.threshold_off}°C. Desligando ventoinha.")
                self.fan.off()

    def _calculate_curve_speed(self, temp: float) -> int:
        """
        Calculate fan speed based on temperature curve.
        Interpolates between curve points.
        """
        if not self.curve_points:
            return 0

        # Sort by temperature
        points = sorted(self.curve_points, key=lambda p: p["temp"])

        # Below first point
        if temp <= points[0]["temp"]:
            return int(points[0]["speed"])

        # Above last point
        if temp >= points[-1]["temp"]:
            return int(points[-1]["speed"])

        # Interpolate between points
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            if p1["temp"] <= temp <= p2["temp"]:
                # Linear interpolation
                ratio = (temp - p1["temp"]) / (p2["temp"] - p1["temp"])
                speed = p1["speed"] + ratio * (p2["speed"] - p1["speed"])
                return int(speed)

        return 0

    def _check_override_timeout(self):
        """Auto-revert manual override after timeout."""
        if self.manual_override and self._last_override_time > 0:
            elapsed = asyncio.get_event_loop().time() - self._last_override_time
            if elapsed >= self._override_timeout:
                self.manual_override = False
                logger.info("Manual override timeout — retornando ao modo automático")
                self._last_override_time = 0

    def set_speed(self, speed_percent: int):
        """Set fan speed manually (0-100)."""
        if not self.fan:
            return

        speed_percent = max(0, min(100, speed_percent))
        self.speed_percent = speed_percent
        self.manual_override = True
        self._last_override_time = asyncio.get_event_loop().time()

        if self.pwm_mode:
            self.fan.value = speed_percent / 100.0
        else:
            if speed_percent > 0:
                self.fan.on()
            else:
                self.fan.off()

        logger.info(f"Fan speed set to {speed_percent}% (manual override)")

    def set_auto(self):
        """Return to automatic temperature-based control."""
        self.manual_override = False
        self._last_override_time = 0
        logger.info("Fan returned to automatic mode")

    def stop(self):
        """Stop the fan control service."""
        self.running = False
        if self.fan:
            self.fan.off()
            try:
                self.fan.close()
            except Exception:
                pass
            self.fan = None
        logger.info("FanControlService parado.")
