"""One latest-frame detection worker, shared by all annotated-camera viewers."""
import asyncio
import os
import time
from pathlib import Path


class BoxService:
    MAX_AGE = 3.0
    INTERVAL = 0.1

    def __init__(self, get_frame, connected, *, clock=time.monotonic):
        self.get_frame = get_frame
        self.connected = connected
        self.clock = clock
        self.weights_path = os.getenv("GO2_DETECTOR_WEIGHTS", str(
            Path(__file__).with_name("models") / "yolo11s.pt"))
        self.model_name = Path(self.weights_path).stem
        self._detector = None
        self._task = None
        self._subscribers = 0
        self._epoch = 0
        self._latest = None
        self._closed = False
        self.state = "idle"
        self.error = ""
        self.device = None
        self.fps = 0.0

    async def infer(self, jpeg):
        # Imports/model loading/prediction all happen off the control event loop.
        def detect():
            if self._detector is None:
                from object_boxes import ObjectBoxDetector
                self._detector = ObjectBoxDetector(self.weights_path)
            return self._detector.detect(jpeg)
        return await asyncio.to_thread(detect)

    def status(self):
        age = None
        count = 0
        if self._latest and self._latest[1] == self.get_frame()[2]:
            age = max(0, self.clock() - self._latest[0])
            if self.connected() and age <= self.MAX_AGE:
                count = len(self._latest[2]["detections"])
        return {"state": self.state, "error": self.error, "model": self.model_name,
                "device": self.device, "count": count,
                "frame_age_seconds": age, "fps": round(self.fps, 1)}

    def invalidate_camera(self):
        self._epoch += 1
        self._latest = None
        self.fps = 0.0

    async def _run(self):
        last_seen = None
        last_completed = None
        self.state = "loading"
        self.error = ""
        try:
            while self._subscribers and not self._closed:
                started = self.clock()
                jpeg, captured_at, session = self.get_frame()
                if (not self.connected() or not jpeg
                        or self.clock() - captured_at > 2
                        or last_seen == (captured_at, session)):
                    await asyncio.sleep(0.05)
                    continue
                last_seen = (captured_at, session)
                epoch = self._epoch
                result = await self.infer(jpeg)
                now = self.clock()
                if (self._subscribers and not self._closed and self.connected()
                        and epoch == self._epoch and session == self.get_frame()[2]
                        and 0 <= now - captured_at <= self.MAX_AGE):
                    self._latest = (captured_at, session, result)
                    self.device = result["device"]
                    self.state = "running"
                    if last_completed is not None and now > last_completed:
                        self.fps = 1 / (now - last_completed)
                    last_completed = now
                await asyncio.sleep(max(0.01, self.INTERVAL - (self.clock() - started)))
        except Exception:
            self._latest = None
            self.state = "error"
            self.error = "Object detector unavailable. Check the model weights and vision dependencies, or turn boxes off for raw video."
        finally:
            if self.state != "error":
                self.state = "idle"

    async def frames(self):
        self._subscribers += 1
        if self._task is None or self._task.done():
            self.state = "loading"
            self.error = ""
            self._task = asyncio.create_task(self._run())
        sent = None
        try:
            while self.connected() and not self._closed:
                latest = self._latest
                if (latest and latest[1] == self.get_frame()[2]
                        and 0 <= self.clock() - latest[0] <= self.MAX_AGE
                        and sent != (latest[0], latest[1])):
                    sent = (latest[0], latest[1])
                    jpeg = latest[2]["jpeg"]
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                           + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                if self.state == "error":
                    return
                await asyncio.sleep(0.04)
        finally:
            self._subscribers -= 1

    async def close(self):
        self._closed = True
        self.invalidate_camera()
        if self._task:
            await self._task
