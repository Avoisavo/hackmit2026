"""Sample the existing camera; never create a robot connection or issue motion."""
import asyncio
import contextlib
import json
import os
import re
import secrets
import time

from fastapi import APIRouter, HTTPException, Request

from object_vision import DEFAULT_MODEL, VisionError, analyze_scene, check_answer, lesson_state, observation_consensus


class VisionService:
    CAMERA_MAX_AGE = 2.0
    OBSERVATION_MAX_AGE = 20.0
    INTERVAL = 8.0
    SESSION_SCANS = 30

    def __init__(self, get_frame, connected, *, clock=time.monotonic, box_status=None):
        self.get_frame = get_frame
        self.connected = connected
        self.clock = clock
        self.box_status = box_status
        self.analyze = analyze_scene
        self.pair_delay = 0.35
        self.model = os.getenv("OPENAI_VISION_MODEL", DEFAULT_MODEL)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", self.model):
            self.model = DEFAULT_MODEL
        self._api_key = os.getenv("OPENAI_API_KEY", "")
        self.target_object = "cups"
        self.target_count = 3
        self.round_id = secrets.token_hex(8)
        self.revision = 0
        self._epoch = 0
        self._observation = None
        self._observation_at = 0.0
        self._observation_id = None
        self._observation_session = None
        self._last_event = None
        self._scan_task = None
        self._runners = set()
        self._wake = asyncio.Event()
        self.running = False
        self.scans_remaining = 0
        self.error = ""
        self.router = APIRouter(prefix="/api/vision")
        self.router.add_api_route("/status", self.status_api, methods=["GET"])
        self.router.add_api_route("/key", self.key_api, methods=["POST"])
        self.router.add_api_route("/round", self.round_api, methods=["POST"])
        self.router.add_api_route("/scan", self.scan_api, methods=["POST"])
        self.router.add_api_route("/start", self.start_api, methods=["POST"])
        self.router.add_api_route("/stop", self.stop_api, methods=["POST"])
        self.router.add_api_route("/answer", self.answer_api, methods=["POST"])

    @property
    def busy(self):
        return self._scan_task is not None and not self._scan_task.done()

    def camera_fresh(self):
        jpeg, at, _ = self.get_frame()
        return bool(self.connected() and jpeg and 0 <= self.clock() - at < self.CAMERA_MAX_AGE)

    def observation_fresh(self):
        return bool(self._observation is not None and self.camera_fresh()
                    and self.get_frame()[2] == self._observation_session
                    and 0 <= self.clock() - self._observation_at <= self.OBSERVATION_MAX_AGE)

    def status(self):
        fresh = self.observation_fresh()
        lesson = None
        if self._observation is not None:
            lesson = lesson_state(self.target_object, self.target_count,
                                  self._observation["observed_count"],
                                  stable=fresh and self._observation["stable"])
        return {
            "configured": bool(self._api_key), "model": self.model,
            "running": self.running, "busy": self.busy, "error": self.error,
            "connected": bool(self.connected()), "camera_fresh": self.camera_fresh(),
            "scans_remaining": self.scans_remaining, "interval_seconds": self.INTERVAL,
            "round_id": self.round_id, "revision": self.revision,
            "target_object": self.target_object, "target_count": self.target_count,
            "observation": self._observation, "observation_id": self._observation_id,
            "observation_fresh": fresh,
            "observation_age_seconds": (max(0, self.clock() - self._observation_at)
                                        if self._observation is not None else None),
            "lesson": lesson, "last_event": self._last_event if fresh else None,
            "boxes": self.box_status() if self.box_status else None,
        }

    def clear_observation(self):
        self._observation = None
        self._observation_id = None
        self._observation_session = None
        self._last_event = None
        self.revision += 1

    def stop_scanning(self):
        self.running = False
        self.scans_remaining = 0
        self._epoch += 1
        self._wake.set()
        # A requests thread cannot be cancelled safely. Keep the busy slot until
        # it exits; its generation no longer has permission to publish a result.

    def invalidate_camera(self):
        self.stop_scanning()
        self.clear_observation()

    def require_ready(self):
        if not self._api_key:
            raise HTTPException(409, "Add an OpenAI API key on this page first.")
        if not self.camera_fresh():
            raise HTTPException(409, "The robot camera is offline or stale. Connect it from Controls first.")

    async def wait_for_pair(self):
        await asyncio.sleep(self.pair_delay)

    async def analyze_pair(self, first, second, api_key, target):
        # Both requests use the same frozen target and key. No retries or
        # overlapping scan cycles, and network calls never block the watchdog.
        results = await asyncio.gather(
            asyncio.to_thread(self.analyze, first, api_key, self.model, target),
            asyncio.to_thread(self.analyze, second, api_key, self.model, target),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return results

    async def _perform_scan(self, epoch):
        try:
            self.require_ready()
            self.error = ""
            first, first_at, camera_session = self.get_frame()
            target, key = self.target_object, self._api_key
            await self.wait_for_pair()
            self.require_ready()
            second, second_at, second_session = self.get_frame()
            if camera_session != second_session or second_at <= first_at:
                raise HTTPException(409, "Waiting for two new camera frames. Try again when video is live.")
            if epoch != self._epoch:
                raise HTTPException(409, "Scan stopped or the activity changed. Result discarded.")
            pair = await self.analyze_pair(first, second, key, target)
            if epoch != self._epoch or camera_session != self.get_frame()[2]:
                raise HTTPException(409, "Scan stopped or the camera/activity changed. Result discarded.")
            if not self.camera_fresh() or self.clock() - first_at > self.OBSERVATION_MAX_AGE:
                raise HTTPException(409, "The camera result is too old. Keep the view still and scan again.")
            self._observation = observation_consensus(*pair)
            self._observation_at = first_at
            self._observation_session = camera_session
            self.revision += 1
            self._observation_id = self.revision
            self._last_event = None
        except (VisionError, ValueError) as exc:
            message = str(exc) if isinstance(exc, VisionError) else "The vision response could not be validated. Please scan again."
            if epoch == self._epoch:
                self.error = message
                self.clear_observation()
            raise HTTPException(502, message) from None
        except HTTPException as exc:
            if epoch == self._epoch:
                self.error = exc.detail
                self.clear_observation()
            raise
        except Exception:
            if epoch == self._epoch:
                self.error = "Vision analysis failed. Please try again."
                self.clear_observation()
            raise HTTPException(502, "Vision analysis failed. Please try again.") from None

    async def scan(self):
        if self.busy:
            raise HTTPException(409, "An analysis is already running. Wait for it to finish.")
        self.require_ready()
        self._scan_task = asyncio.create_task(self._perform_scan(self._epoch))
        # Disconnecting a browser must not free the in-flight network slot.
        # Retrieve eventual errors even when no caller remains to await them.
        self._scan_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        await asyncio.shield(self._scan_task)
        return self.status()

    async def _run(self, epoch, wake):
        try:
            while self.running and epoch == self._epoch and self.scans_remaining:
                self.scans_remaining -= 1
                await self.scan()
                if self.scans_remaining:
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(wake.wait(), timeout=self.INTERVAL)
        except HTTPException as exc:
            if epoch == self._epoch:
                self.error = exc.detail
                self.clear_observation()
        finally:
            if epoch == self._epoch:
                self.running = False
                self.scans_remaining = 0

    async def close(self):
        self.stop_scanning()
        tasks = list(self._runners)
        if self._scan_task is not None:
            tasks.append(self._scan_task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._api_key = ""

    @staticmethod
    async def body(request):
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > 4096:
                raise HTTPException(400, "Request is too large.")
        try:
            value = json.loads(payload)
        except (ValueError, UnicodeError):
            raise HTTPException(400, "Send a valid JSON object.") from None
        if not isinstance(value, dict):
            raise HTTPException(400, "Send a valid JSON object.")
        return value

    async def status_api(self):
        return self.status()

    async def key_api(self, request: Request):
        value = (await self.body(request)).get("api_key")
        if (not isinstance(value, str) or not 10 <= len(value) <= 512
                or not value.isascii() or any(ch.isspace() for ch in value)
                or not value.startswith("sk-")):
            raise HTTPException(400, "Enter a valid OpenAI API key without whitespace.")
        self.stop_scanning()
        self.clear_observation()
        self._api_key = value
        self.error = ""
        return self.status()

    async def round_api(self, request: Request):
        body = await self.body(request)
        try:
            state = lesson_state(body.get("target_object"), body.get("target_count"), None)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        self.stop_scanning()
        self.clear_observation()
        self.target_object, self.target_count = state["target_object"], state["target_count"]
        self.round_id = secrets.token_hex(8)
        self.error = ""
        return self.status()

    async def scan_api(self):
        if self.running:
            raise HTTPException(409, "Live scanning is already running.")
        return await self.scan()

    async def start_api(self):
        if self.running:
            return self.status()
        if self.busy:
            raise HTTPException(409, "Wait for the current analysis to finish.")
        self.require_ready()
        self._epoch += 1
        self._wake = asyncio.Event()
        self.running = True
        self.scans_remaining = self.SESSION_SCANS
        self.error = ""
        task = asyncio.create_task(self._run(self._epoch, self._wake))
        self._runners.add(task)
        task.add_done_callback(self._runners.discard)
        return self.status()

    async def stop_api(self):
        self.stop_scanning()
        return self.status()

    async def answer_api(self, request: Request):
        body = await self.body(request)
        if (body.get("round_id") != self.round_id
                or type(body.get("observation_id")) is not int
                or body["observation_id"] != self._observation_id):
            raise HTTPException(409, "The activity or camera observation changed. Use the current question.")
        if not self.observation_fresh() or not self._observation["stable"]:
            raise HTTPException(409, "Get a fresh, clear count before checking an answer.")
        try:
            event = check_answer(self.target_object, self.target_count,
                                 self._observation["observed_count"], body.get("answer"),
                                 stable=True, fresh=True)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        self.revision += 1
        self._last_event = {**event, "event_id": self.revision}
        return self.status()
