"""Recover transports without replaying a movement command."""
import asyncio
import contextlib
import logging

logger = logging.getLogger(__name__)


def guard_heartbeat(heartbeat):
    """SDK 2.2.0 stops scheduling heartbeats if one publish raises."""
    original_send = heartbeat.send_heartbeat

    def send():
        try:
            original_send()
        except Exception:
            logger.warning("Robot heartbeat send failed; retrying in 2 seconds", exc_info=True)
            if heartbeat.channel.readyState == "open":
                heartbeat.start_heartbeat()

    heartbeat.stop_heartbeat()
    heartbeat.send_heartbeat = send
    heartbeat.start_heartbeat()


class ConnectionSupervisor:
    POLL = 0.5
    GRACE = 3.0
    RETRY_DELAYS = (0, 2, 5)

    def __init__(self, connected, busy, reconnect, on_loss):
        self.connected = connected
        self.busy = busy
        self.reconnect = reconnect
        self.on_loss = on_loss
        self.task = None
        self.reconnecting = False
        self.attempt = 0
        self.message = ""

    def start(self):
        if self.task is None or self.task.done():
            self.attempt = 0
            self.message = ""
            self.task = asyncio.create_task(self._run())

    async def stop(self):
        task, self.task = self.task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.reconnecting = False
        self.attempt = 0
        self.message = ""

    async def _run(self):
        try:
            while True:
                await asyncio.sleep(self.POLL)
                if self.connected():
                    continue
                self.on_loss()
                self.reconnecting = True
                self.attempt = 0
                self.message = "Robot link interrupted. Movement stopped; waiting for the link."
                logger.warning(self.message)
                # Let a transient ICE interruption settle without replacing a
                # peer that may still recover on its own.
                await asyncio.sleep(self.GRACE)
                for attempt, delay in enumerate(self.RETRY_DELAYS, 1):
                    await asyncio.sleep(delay)
                    while self.busy() and not self.connected():
                        await asyncio.sleep(self.POLL)
                    if self.connected():
                        break
                    self.attempt = attempt
                    self.message = f"Reconnecting robot ({attempt}/{len(self.RETRY_DELAYS)}). Movement is disarmed."
                    logger.warning(self.message)
                    try:
                        await self.reconnect()
                    except Exception:
                        logger.warning("Robot reconnect attempt failed", exc_info=True)
                    if self.connected():
                        break
                self.reconnecting = False
                if not self.connected():
                    self.message = "Robot reconnection failed. Check Wi-Fi and the robot IP, then click Connect robot."
                    logger.warning(self.message)
                    return
                self.message = "Robot link restored. Release movement keys, then press again to drive."
                self.attempt = 0
                logger.info(self.message)
        finally:
            self.reconnecting = False
