import asyncio
import logging
import time
from typing import Dict, Any, List, Set, Optional

from jarvis.core.context_reader import ContextReader
from jarvis.modules.network import NetworkModule
from jarvis.database.persistence import Persistence

logger = logging.getLogger("services.guardian")


class GuardianService:
    """
    GuardianService — O Guardião da Casa e da Rede.

    Filosofia:
    - Percepção > Notificação.
    - Silêncio é o padrão. Só fala se for relevante.
    - Linguagem natural e humana. Zero "robotic alerts".
    """

    def __init__(
        self,
        application,
        chat_id: int,
        interval_seconds: int = 1, # Loop rápido para controle interno
    ):
        self.app = application
        self.chat_id = chat_id
        self.running = False

        # Configurações de Tempo
        self.PING_INTERVAL = 15
        self.DEVICE_SCAN_INTERVAL = 60
        self.POWER_GAP_THRESHOLD_MINUTES = 2

        # Estado Interno - Internet
        self.internet_state = "online"  # online, unstable, offline
        self.consecutive_ping_failures = 0
        self.last_ping_time = 0
        self.latency_history: List[float] = []

        # Estado Interno - Dispositivos
        self.last_device_scan_time = 0
        self.online_macs: Optional[Set[str]] = None

        # Filas de Notificação
        self.pending_power_msg: Optional[str] = None

    async def start(self):
        if self.running:
            return

        self.running = True
        logger.info("🛡 GuardianService iniciado (Modo: Guardião Silencioso).")

        # 1. Checagem inicial de Queda de Energia
        await self.check_power_status()

        # Loop Principal
        while self.running:
            try:
                now = time.time()

                # Tique da Internet (15s)
                if now - self.last_ping_time >= self.PING_INTERVAL:
                    await self.check_internet_status()
                    self.last_ping_time = now

                # Tique dos Dispositivos (60s)
                if now - self.last_device_scan_time >= self.DEVICE_SCAN_INTERVAL:
                    await self.check_device_changes()
                    self.last_device_scan_time = now

            except Exception as e:
                logger.error(f"Erro no loop do Guardian: {e}")
                await asyncio.sleep(5)

            await asyncio.sleep(1)

    # =========================================================================
    # ⚡ ENERGIA
    # =========================================================================
    async def check_power_status(self):
        """
        Verifica se houve um 'gap' nos registros indicando queda de energia anterior.
        """
        try:
            # Verifica gap nos últimos minutos (baseado no timestamp do último snapshot)
            result = ContextReader.detect_gap(max_gap_minutes=self.POWER_GAP_THRESHOLD_MINUTES)

            if result.get("status") == "ok" and result.get("exceeded"):
                gap = result.get("gap_minutes", 0)

                # Só avisa se for algo relevante (> 2 min)
                if gap >= 10:
                    msg = (
                        f"Ei, a energia caiu e ficou fora por uns {int(gap)} minutos. "
                        "Já conferi os serviços e tá tudo ok."
                    )
                else:
                    msg = "Parece que a energia caiu por um tempo. Agora voltou e tô subindo tudo de novo."

                # Não envia imediatamente, pois a internet pode estar voltando.
                # Coloca na fila.
                self.pending_power_msg = msg
                logger.info(f"Queda de energia detectada. Mensagem na fila: {msg}")

        except Exception as e:
            logger.error(f"Erro ao verificar status de energia: {e}")

    # =========================================================================
    # 🌐 INTERNET
    # =========================================================================
    async def check_internet_status(self):
        metrics = await NetworkModule.get_ping_metrics()
        success = metrics.get("success", False)
        latency = metrics.get("latency_ms")

        if success:
            # -------------------------------------------------
            # CASO: SUCESSO
            # -------------------------------------------------

            # Recuperação de Queda
            if self.internet_state == "offline":
                await self.send_message("A internet voltou agora. Tudo subindo aos poucos por aqui.")
                self.internet_state = "online"
                self.consecutive_ping_failures = 0

            # Recuperação de Instabilidade
            elif self.internet_state == "unstable":
                if self.consecutive_ping_failures > 0:
                    self.consecutive_ping_failures = 0
                self.internet_state = "online"

            # Monitoramento de Latência (apenas se online)
            if latency:
                self.latency_history.append(latency)
                self.latency_history = self.latency_history[-10:]

            # FLUSH QUEUE: Se a internet está OK, envia mensagens pendentes (ex: energia)
            if self.pending_power_msg:
                sent = await self.send_message(self.pending_power_msg)
                if sent:
                    self.pending_power_msg = None

        else:
            # -------------------------------------------------
            # CASO: FALHA
            # -------------------------------------------------
            self.consecutive_ping_failures += 1

            # 1 falha = ignora (glitch)
            if self.consecutive_ping_failures == 1:
                pass

            # 2 falhas = Piscada / Instabilidade
            elif self.consecutive_ping_failures == 2:
                if self.internet_state == "online":
                    sent = await self.send_message("A internet deu uma piscada rápida aqui. Se continuar, te aviso.")
                    if sent:
                        self.internet_state = "unstable"
                    # Se não enviou, provavelmente já caiu de vez.

            # 3 falhas (45s) = Queda provável
            elif self.consecutive_ping_failures == 3:
                if self.internet_state != "offline":
                    sent = await self.send_message("Ei… a internet caiu agora. Pode ter sido o provedor. Vou testar de novo em instantes.")
                    if sent:
                        self.internet_state = "offline"
                    else:
                        # Se falhou ao enviar, assumimos offline silenciosamente (bot não consegue falar)
                        self.internet_state = "offline"

    # =========================================================================
    # 🕵️‍♂️ DISPOSITIVOS
    # =========================================================================
    async def check_device_changes(self):
        try:
            snapshot = await NetworkModule.get_raw_snapshot()
            devices = snapshot.get("devices", [])

            current_macs = {d["mac"] for d in devices}

            # Inicialização
            if self.online_macs is None:
                self.online_macs = current_macs
                return

            # Diferenças
            joined = current_macs - self.online_macs
            left = self.online_macs - current_macs

            self.online_macs = current_macs

            # Processar Entradas
            for mac in joined:
                await self.handle_device_joined(mac, devices)

            # Processar Saídas
            for mac in left:
                await self.handle_device_left(mac)

        except Exception as e:
            logger.error(f"Erro no scan de dispositivos: {e}")

    async def handle_device_joined(self, mac: str, all_devices: List[Dict]):
        # Identificar dispositivo
        device_info = next((d for d in all_devices if d["mac"] == mac), None)
        ip = device_info["ip"] if device_info else "?"

        # Enriquecer dados (Nome, Vendor)
        name = Persistence.get_device_name(mac)

        if not name:
            await self.send_message(
                f"Entrou um dispositivo novo na rede agora. IP {ip}. Quer que eu marque?"
            )
        else:
            await self.send_message(
                f"Ei, alguém acabou de conectar na rede: {name} ({ip})."
            )

    async def handle_device_left(self, mac: str):
        name = Persistence.get_device_name(mac)

        if name:
            await self.send_message(f"O {name} saiu da rede.")
        else:
            pass

    # =========================================================================
    # 📢 COMUNICAÇÃO
    # =========================================================================
    async def send_message(self, text: str) -> bool:
        """
        Envia mensagem direta. Retorna True se sucesso, False se falha.
        """
        try:
            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=text
            )
            return True
        except Exception as e:
            logger.warning(f"Guardian não conseguiu enviar mensagem: {e}")
            return False
