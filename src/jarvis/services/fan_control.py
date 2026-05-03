import asyncio
import logging
from jarvis.modules.system import SystemModule
from jarvis.config import Config

logger = logging.getLogger("services.fan_control")

class FanControlService:
    """
    Serviço para controle automático da ventoinha do Raspberry Pi
    baseado na temperatura da CPU utilizando gpiozero.
    """

    def __init__(self, pin: int = 14, threshold_on: float = 60.0, threshold_off: float = 50.0, interval_seconds: int = 10):
        self.pin = pin
        self.threshold_on = threshold_on
        self.threshold_off = threshold_off
        self.interval = interval_seconds
        self.running = False
        self.fan = None
        self._init_gpio()

    def _init_gpio(self):
        try:
            from gpiozero import OutputDevice
            # Active high by default for typical transistor circuits
            self.fan = OutputDevice(self.pin)
            logger.info(f"FanControlService inicializado no GPIO {self.pin}")
        except Exception as e:
            logger.error(f"Erro ao inicializar gpiozero: {e}. O fan control não funcionará.")
            self.fan = None

    async def start(self):
        if self.running:
            return
        self.running = True
        logger.info("🌬️ FanControlService iniciado.")

        while self.running:
            if self.fan is not None:
                try:
                    await self._check_temperature()
                except Exception as e:
                    logger.error(f"Erro no loop do FanControlService: {e}")
            await asyncio.sleep(self.interval)

    async def _check_temperature(self):
        raw_status = await SystemModule.get_raw_status()
        temp = raw_status.get("temperature_c")

        if temp is not None:
            if temp >= self.threshold_on and not self.fan.is_active:
                logger.info(f"Temperatura {temp}°C >= {self.threshold_on}°C. Ligando ventoinha.")
                self.fan.on()
            elif temp <= self.threshold_off and self.fan.is_active:
                logger.info(f"Temperatura {temp}°C <= {self.threshold_off}°C. Desligando ventoinha.")
                self.fan.off()

    def stop(self):
        self.running = False
        if self.fan:
            self.fan.off()
            self.fan.close()
            self.fan = None
