"""One activity owner for camera observations, speech, expressions and gestures.

The robot app owns actuators. Device credentials only permit one narrow role.
No provider call or browser event is allowed to advance an obsolete session.
"""
import asyncio
import contextlib
import json
import io
import math
import struct
import wave
import os
import re
import secrets
import time
from collections import deque

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

EMOTES = ("Ready", "Watching", "Encourage", "Thinking", "Go", "Celebrate", "Rest", "Soft confused")
ROLES = ("mic", "speaker", "face")
WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def number_answer(text):
    if re.search(r"\b(minus|negative|point|half|hundred|thousand|million|eleven|twelve|\w+teen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)\b|[-+]\s*\d|\d[.,]\d", text.lower()):
        return None
    words = dict(zip(WORDS, range(11)))
    words.update(won=1, to=2, too=2, tree=3, ate=8)
    found = set()
    for word in re.findall(r"\b\d+\b|[a-z]+", text.lower()):
        if word.isdigit():
            if len(word) > 2:
                return None
            found.add(int(word))
        elif word in words:
            found.add(words[word])
    return next(iter(found)) if len(found) == 1 else None


async def body(request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise HTTPException(400, "Request too large")
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError):
        raise HTTPException(400, "Expected a JSON object") from None


class AudioProviders:
    def __init__(self):
        self.deepgram = os.getenv("DEEPGRAM_API_KEY", "")
        self.elevenlabs = os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")

    @staticmethod
    def post(url, **kwargs):
        try:
            response = requests.post(url, timeout=(5, 25), allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise HTTPException(502, "Voice provider unavailable or timed out") from None
        if response.status_code not in (200, 201):
            raise HTTPException(502, "Voice provider rejected the request; check credentials and account access")
        return response

    def token(self):
        if not self.deepgram:
            raise HTTPException(409, "Configure the Deepgram API key first")
        response = self.post("https://api.deepgram.com/v1/auth/grant",
            headers={"Authorization": "Token " + self.deepgram}, json={"ttl_seconds": 60})
        try:
            data = response.json()
            token = data["access_token"]
            if not isinstance(token, str) or not token:
                raise ValueError()
            return {"access_token": token}
        except (KeyError, TypeError, ValueError):
            raise HTTPException(502, "Deepgram returned an invalid credential") from None

    @staticmethod
    def tone():
        rate, seconds = 24000, 0.8
        samples = bytearray()
        for i in range(int(rate * seconds)):
            t = i / rate
            envelope = min(1, t / 0.02, (seconds - t) / 0.05)
            samples.extend(struct.pack("<h", round(4500 * envelope * math.sin(2 * math.pi * 660 * t))))
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
            wav.writeframes(samples)
        return output.getvalue()

    def speak(self, text):
        if not self.elevenlabs or not self.voice_id:
            raise HTTPException(409, "Configure ElevenLabs API key and voice ID first")
        response = self.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream?output_format=mp3_22050_32",
            headers={"xi-api-key": self.elevenlabs, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_flash_v2_5"})
        if not response.headers.get("content-type", "").startswith("audio/") or not 1 <= len(response.content) <= 8_000_000:
            raise HTTPException(502, "ElevenLabs returned invalid audio")
        return response.content


class ControlPlane:
    DEVICE_TIMEOUT = 4
    SPEECH_TIMEOUT = 60
    SESSION_SECONDS = 600

    def __init__(self, *, vision, acquire, check_context, stop_robot, gesture, finish, speaker=None, audio_acquire=None, audio_check=None, clock=time.monotonic):
        self.vision = vision
        self.acquire, self.check_context = acquire, check_context
        self.stop_robot, self.gesture, self.finish = stop_robot, gesture, finish
        self.clock = clock
        self.audio = AudioProviders()
        self.speaker = speaker
        self.audio_acquire = audio_acquire
        self.audio_check = audio_check
        self._test_playback = None
        self.speaker_output = "go2" if speaker else "browser"
        self._speech_task = None
        self._test_task = None
        self._test_id = ""
        self._mic_until = 0
        self.test = {"kind": "", "status": "idle", "message": "Choose a component to test."}
        self.devices = {}
        self.running = False
        self.session_id = ""
        self.phase = "idle"
        self.face = "Ready"
        self.message = "Enable a computer speaker, test the sound, then connect Go2 for the blocks activity."
        self.target = 3
        self.observed = None
        self.question_id = ""
        self.speech = None
        self.answer_correct = False
        self.task_complete = False
        self.events = deque(maxlen=60)
        self.seen_events = deque(maxlen=200)
        self._task = None
        self._gesture_task = None
        self._context = None
        self._next_scan = 0
        self._pending_observation = None
        self._audio_job = None
        self._audio_id = ""
        self._audio_bytes = None
        self._token_at = float("-inf")
        self._token_busy = False
        self.router = APIRouter()
        for path, method, handler in [
            ("/api/plane/status", "GET", self.status),
            ("/api/plane/keys", "POST", self.keys_api),
            ("/api/plane/pair", "POST", self.pair_api),
            ("/api/plane/start", "POST", self.start_api),
            ("/api/plane/stop", "POST", self.stop_api),
            ("/api/plane/answer", "POST", self.operator_answer_api),
            ("/api/plane/face", "POST", self.face_api),
            ("/api/plane/test", "POST", self.test_api),
            ("/session/state", "GET", self.device_state),
            ("/session/transcript", "POST", self.transcript_api),
            ("/session/speech", "POST", self.speech_api),
            ("/session/fault", "POST", self.fault_api),
            ("/session/deepgram", "POST", self.token_api),
            ("/session/audio", "GET", self.audio_api),
        ]:
            self.router.add_api_route(path, handler, methods=[method])

    @property
    def busy(self):
        return any(task and not task.done() for task in (self._task, self._gesture_task, self._audio_job, self._speech_task, self._test_task))

    def log(self, kind, text):
        self.events.append({"id": secrets.token_hex(6), "kind": kind, "text": text})

    def online(self, role):
        device = self.devices.get(role)
        return bool(device and device["owner"] and self.clock() - device["at"] < self.DEVICE_TIMEOUT)

    def status(self):
        return {"running": self.running, "busy": self.busy, "session_id": self.session_id,
                "phase": self.phase, "face": self.face, "message": self.message,
                "target": self.target, "observed": self.observed, "question_id": self.question_id,
                "speech": self.speech, "answer_correct": self.answer_correct,
                "task_complete": self.task_complete, "events": list(self.events),
                "devices": {role: {"paired": role in self.devices, "online": self.online(role)} for role in ROLES},
                "test": dict(self.test), "speaker_output": self.speaker_output,
                "speaker": self.speaker.status() if self.speaker else {"output": "browser", "ready": self.online("speaker"), "message": "Go2 Air uses the computer or a paired external speaker for sound."},
                "configured": {"openai": bool(self.vision._api_key), "deepgram": bool(self.audio.deepgram),
                    "elevenlabs": bool(self.audio.elevenlabs and self.audio.voice_id)}}

    def cancel(self, reason="Activity stopped"):
        self._test_id = ""
        self._mic_until = 0
        if self.test["status"] == "running":
            self.test.update(status="stopped", message=reason)
        if self.speaker:
            self.speaker.stop()
        if not self.running:
            self.speech = None
            return
        self.running = False
        self.phase = "stopped"
        self.face = "Ready"
        self.message = reason
        self.speech = None
        self.question_id = ""
        self._pending_observation = None
        self.vision.stop_scanning()
        self.log("stop", reason)

    def check(self, session_id, *, decision=False):
        if not self.running or session_id != self.session_id:
            raise HTTPException(409, "Activity was stopped or replaced")
        self.check_context(self._context)
        if not self.vision.camera_fresh():
            raise HTTPException(409, "Camera is stale; activity stopped")
        if not self.speaker_ready():
            raise HTTPException(409, "Speaker disconnected; activity stopped")
        if self._require_mic and not self.online("mic"):
            raise HTTPException(409, "Microphone disconnected; activity stopped")
        if self.clock() >= self._deadline:
            raise HTTPException(409, "Activity time limit reached")

    def say(self, text, after, face):
        self.phase = "speaking"
        self.face = face
        self.message = text
        self.speech = {"id": secrets.token_hex(12), "text": text, "status": "queued"}
        self._speech_at = self.clock()
        self._after_speech = after
        self._audio_bytes = None
        self.log("voice", text)
        if self.speaker_output == "go2":
            self._speech_task = asyncio.create_task(self.robot_speech(self.session_id, self.speech["id"], text))

    def speaker_ready(self):
        return self.speaker.ready() if self.speaker_output == "go2" else self.online("speaker")

    def speech_ended(self):
        self.speech = None
        self.phase = self._after_speech
        if self._pending_observation:
            self._pending_observation = None
            self.observation(self.vision.status())

    async def robot_speech(self, session_id, speech_id, text):
        def check():
            self.check(session_id)
            if not self.speech or self.speech["id"] != speech_id:
                raise HTTPException(409, "Speech canceled")
        try:
            check()
            audio = await asyncio.to_thread(self.audio.speak, text)
            check()
            self.speech["status"] = "playing"
            await self.speaker.play(audio, check)
            check()
            self.speech_ended()
        except Exception as exc:
            if self.running and self.session_id == session_id:
                reason = str(exc.detail) if isinstance(exc, HTTPException) else "Go2 speech failed; check voice settings and robot audio"
                self.stop_robot(reason)

    def observation(self, state):
        if not self.running:
            return
        if self.phase == "speaking":
            self._pending_observation = state
            return
        if self.phase not in ("observing", "waiting_answer"):
            return
        observation = state.get("observation")
        if not state.get("observation_fresh") or not observation or not observation.get("stable"):
            self.observed = None
            self.question_id = ""
            self.phase, self.face = "observing", "Soft confused"
            self.message = "Waiting for two clear, agreeing camera counts of the toy blocks."
            return
        count = observation["observed_count"]
        if type(count) is not int or not 0 <= count <= 20:
            return
        same_question = self.phase == "waiting_answer" and count == self.observed
        unchanged_extra = self.phase == "observing" and count == self.observed and count > self.target
        self.observed = count
        if same_question or unchanged_extra:
            return
        if count == 0:
            self.phase, self.face = "observing", "Watching"
            self.question_id = ""
            self.message = "Waiting for toy blocks in the camera view."
            return
        self.log("camera", f"Stable observation: {count} toy blocks")
        if count == self.target:
            self.task_complete = True
            self.say(f"Now I can see all {WORDS[self.target]} blocks. You did it!", "celebrating", "Celebrate")
            self.start_gesture()
        elif count > self.target:
            self.say(f"I can see {count} blocks. We need {WORDS[self.target]}. Can you take some away?",
                     "observing", "Encourage")
        else:
            self.question_id = secrets.token_hex(12)
            self.say(f"I can see {WORDS[count]} {'block' if count == 1 else 'blocks'}. We need {WORDS[self.target]}. How many more do we need?",
                     "waiting_answer", "Thinking")

    def answer(self, data):
        if not self.running or data.get("session_id") != self.session_id:
            raise HTTPException(409, "This activity is no longer active")
        event_id = data.get("event_id")
        if not isinstance(event_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", event_id):
            raise HTTPException(400, "Invalid event ID")
        if event_id in self.seen_events:
            return
        text = data.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 300 or not text.isprintable():
            raise HTTPException(400, "Enter a short spoken answer")
        if re.fullmatch(r"\s*(stop|stop please|please stop|goodbye|bye|take a break)[.!?]*\s*", text, re.I):
            self.stop_robot("Child requested a stop")
            return
        if self.phase != "waiting_answer" or data.get("question_id") != self.question_id:
            raise HTTPException(409, "Wait for the current question to finish")
        self.check(self.session_id)
        current = self.vision.status()
        if (not current.get("observation_fresh") or not current.get("observation", {}).get("stable")
                or current["observation"]["observed_count"] != self.observed):
            self.phase, self.face = "observing", "Watching"
            self.question_id = ""
            self._next_scan = 0
            raise HTTPException(409, "The view changed or count expired; checking the blocks again")
        self.seen_events.append(event_id)
        self.log("child", text)
        n = number_answer(text)
        missing = self.target - self.observed
        self.question_id = secrets.token_hex(12)  # each spoken question owns its next answer
        if n == missing:
            self.answer_correct = True
            self.say(f"Yes! We need {WORDS[missing]} more. Great thinking!", "celebrating", "Celebrate")
            self.start_gesture()
        elif n is None:
            self.say("I didn't quite hear one answer. How many more blocks do we need?", "waiting_answer", "Encourage")
        else:
            self.say(f"Good try! We have {WORDS[self.observed]} and need {WORDS[self.target]}. How many more do we need?",
                     "waiting_answer", "Encourage")

    def start_gesture(self):
        if not self._wave or self._gesture_task is not None:
            return
        session_id = self.session_id
        async def perform():
            try:
                self.check(session_id)
                await self.gesture(lambda **kw: self.check(session_id, **kw))
                self.check(session_id)
                self.log("robot", "Hello accepted; movement remains disarmed")
            except Exception:
                if self.running and self.session_id == session_id:
                    self.stop_robot("Robot gesture failed or was interrupted")
        self._gesture_task = asyncio.create_task(perform())

    async def run(self, session_id):
        try:
            while self.running and self.session_id == session_id:
                self.check(session_id)
                if self.speech and self.clock() - self._speech_at >= self.SPEECH_TIMEOUT:
                    raise HTTPException(409, "Speech playback timed out")
                if self.phase == "celebrating" and (not self._gesture_task or self._gesture_task.done()):
                    self.finish(self._context)
                    self.running = False
                    self.phase = "complete"
                    self.message = "Activity complete. Movement is disarmed."
                    return
                if self.phase in ("observing", "waiting_answer") and self.clock() >= self._next_scan:
                    state = await self.vision.scan()
                    self.check(session_id)
                    self.observation(state)
                    self._next_scan = self.clock() + 4
                await asyncio.sleep(0.1)
        except Exception as exc:
            if self.running and self.session_id == session_id:
                reason = str(exc.detail) if isinstance(exc, HTTPException) else "Activity failed; movement stopped"
                self.stop_robot(reason)

    async def keys_api(self, request: Request):
        if self.running or self.busy:
            raise HTTPException(409, "Stop the activity and wait for pending work before changing keys")
        data = await body(request)
        allowed = {"openai", "deepgram", "elevenlabs", "voice_id"}
        if set(data) - allowed:
            raise HTTPException(400, "Unknown credential field")
        for name, value in data.items():
            if not isinstance(value, str) or not 1 <= len(value) <= 512 or not value.isascii() or any(c.isspace() for c in value):
                raise HTTPException(400, "Credentials must be ASCII without whitespace")
            if name == "voice_id" and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
                raise HTTPException(400, "Invalid voice ID")
        for name, value in data.items():
            if name == "openai":
                self.vision._api_key = value
            else:
                setattr(self.audio, name, value)
        return self.status()

    async def pair_api(self, request: Request):
        role = (await body(request)).get("role")
        if role not in ROLES:
            raise HTTPException(400, "Unknown device role")
        if self.running:
            raise HTTPException(409, "Stop the activity before pairing or replacing a device")
        key = secrets.token_urlsafe(32)
        self.devices[role] = {"key": key, "owner": "", "at": 0}
        return {"role": role, "path": f"/device/{role}#key={key}", "key": key}

    def device(self, request, role=None):
        key = request.headers.get("X-Device-Key", "")
        client_id = request.query_params.get("client_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", client_id) or not key.isascii() or len(key) > 128:
            raise HTTPException(403, "Invalid device credential")
        found = next(((r, d) for r, d in self.devices.items() if secrets.compare_digest(d["key"], key)), None)
        if not found or role and found[0] != role:
            raise HTTPException(403, "Pair this device again from the control plane")
        r, d = found
        if d["owner"] and d["owner"] != client_id and self.online(r):
            raise HTTPException(409, "Another tab owns this device role")
        if d["owner"] and d["owner"] != client_id and self.running:
            self.stop_robot("Device ownership changed; restart the activity")
        d["owner"], d["at"] = client_id, self.clock()
        return r

    async def device_state(self, request: Request):
        role = self.device(request)
        return {"session_id": self._test_id if self.mic_testing() or self.browser_test() else self.session_id, "running": self.running or self.browser_test(), "phase": self.phase,
                "face": self.face, "task_complete": self.task_complete, "target": self.target,
                "question_id": self.question_id, "listen": self.mic_testing() or (self.running and self.phase == "waiting_answer"),
                "speech": self.speech if role == "speaker" and self.speaker_output == "browser" else None,
                "message": self.message}

    async def start_api(self, request: Request):
        data = await body(request)
        if self.running or self.busy:
            raise HTTPException(409, "An activity or pending operation is still active")
        target = data.get("target", 3)
        if type(target) is not int or not 1 <= target <= 10 or type(data.get("wave", False)) is not bool:
            raise HTTPException(400, "Choose a target from 1–10 and a boolean gesture option")
        if not self.speaker_ready() or not self.audio.elevenlabs or not self.audio.voice_id:
            raise HTTPException(409, "Configure ElevenLabs and connect the selected speaker before starting")
        if not self.vision._api_key or not self.vision.camera_fresh() or self.vision.busy:
            raise HTTPException(409, "Configure OpenAI and wait for a fresh, idle Go2 camera")
        context = self.acquire(data.get("control_id"), data.get("control_epoch"))
        self.vision.stop_scanning()
        self.vision.clear_observation()
        self.vision.target_object = "toy blocks"
        self.vision.target_count = target
        self.vision.round_id = secrets.token_hex(8)
        self._context, self.target = context, target
        self.session_id = secrets.token_hex(16)
        self.events.clear()
        self.seen_events.clear()
        self.running = True
        self.observed = None
        self.question_id = ""
        self.answer_correct = self.task_complete = False
        self._wave = data.get("wave", False)
        self._require_mic = self.online("mic")
        self._gesture_task = None
        self._pending_observation = None
        self._next_scan = 0
        self._deadline = self.clock() + self.SESSION_SECONDS
        self.say(f"Let's build together! Can you put {WORDS[target]} {'block' if target == 1 else 'blocks'} in front of me?", "observing", "Watching")
        self._task = asyncio.create_task(self.run(self.session_id))
        return self.status()

    async def stop_api(self):
        self.stop_robot("Activity stopped by operator")
        return self.status()

    async def operator_answer_api(self, request: Request):
        self.answer(await body(request))
        return self.status()

    async def face_api(self, request: Request):
        name = (await body(request)).get("name")
        if name not in EMOTES:
            raise HTTPException(400, "Unknown expression")
        if self.running:
            raise HTTPException(409, "The activity currently owns the face")
        self.face = name
        return self.status()

    async def transcript_api(self, request: Request):
        self.device(request, "mic")
        data = await body(request)
        if self.mic_testing() and data.get("session_id") == self._test_id:
            text = data.get("text")
            if not isinstance(text, str) or not 1 <= len(text) <= 300 or not text.isprintable():
                raise HTTPException(400, "Invalid test transcript")
            self.test.update(message="Heard: " + text, transcript=text)
            self.log("microphone test", text)
            return {"accepted": True, "test": True}
        self.answer(data)
        return {"accepted": True}

    async def speech_api(self, request: Request):
        self.device(request, "speaker")
        if self.speaker_output != "browser":
            raise HTTPException(409, "Go2 owns speech playback")
        data = await body(request)
        if self.browser_test():
            if data.get("session_id") != self._test_id or not self.speech or data.get("speech_id") != self.speech["id"]:
                raise HTTPException(409, "This speaker test was stopped or replaced")
            event = data.get("status")
            if event == "started":
                if self.speech["status"] == "queued": self.speech["status"] = "playing"
            elif event == "ended":
                if self.speech["status"] != "playing": raise HTTPException(409, "Playback has not started")
                self.speech["status"] = "ended"
                self._test_playback.set()
            elif event == "error":
                self.stop_robot("Browser could not play the test; enable its speaker and retry")
            else:
                raise HTTPException(400, "Unknown playback event")
            return {"accepted": True}
        if (not self.running or data.get("session_id") != self.session_id or not self.speech
                or data.get("speech_id") != self.speech["id"]):
            raise HTTPException(409, "Speech was canceled or replaced")
        event = data.get("status")
        if event == "error":
            self.stop_robot("Speaker could not play the line; activity stopped")
        elif event == "started":
            if self.speech["status"] != "queued":
                return {"accepted": True}
            self.speech["status"] = "playing"
        elif event == "ended":
            if self.speech["status"] != "playing":
                raise HTTPException(409, "Playback has not started")
            self.speech_ended()
        else:
            raise HTTPException(400, "Unknown playback event")
        return {"accepted": True}

    async def fault_api(self, request: Request):
        role = self.device(request)
        self.devices[role]["at"] = float("-inf")
        if (role == "mic" or role == "speaker" and self.speaker_output == "browser") and (self.running or self.browser_test() or self.mic_testing()):
            self.stop_robot(f"{role.capitalize()} disconnected or stopped")
        return {"stopped": True}

    async def token_api(self, request: Request):
        self.device(request, "mic")
        if self._token_busy or self.clock() - self._token_at < 10:
            raise HTTPException(429, "Wait briefly before reconnecting the microphone")
        self._token_busy = True
        self._token_at = self.clock()
        try:
            result = await asyncio.to_thread(self.audio.token)
            self.device(request, "mic")
            return result
        finally:
            self._token_busy = False

    async def audio_api(self, request: Request):
        self.device(request, "speaker")
        if self.speaker_output != "browser":
            raise HTTPException(409, "Go2 owns speech playback")
        speech_id = request.query_params.get("speech_id")
        if not (self.running or self.browser_test()) or not self.speech or speech_id != self.speech["id"]:
            raise HTTPException(409, "This speech is no longer active")
        text = self.speech["text"]
        if self._audio_id != speech_id:
            if self._audio_job and not self._audio_job.done():
                raise HTTPException(409, "Previous audio request is still pending")
            self._audio_id = speech_id
            work = (lambda: self.audio.tone()) if self.speech.get("kind") == "tone" else (lambda: self.audio.speak(text))
            self._audio_job = asyncio.create_task(asyncio.to_thread(work))
        try:
            audio = await asyncio.shield(self._audio_job)
        except Exception:
            if (self.running or self.browser_test()) and self.speech and self.speech["id"] == speech_id:
                self.stop_robot("Speech generation failed; check voice credentials")
            raise HTTPException(502, "Speech generation failed") from None
        self.device(request, "speaker")
        if not (self.running or self.browser_test()) or not self.speech or self.speech["id"] != speech_id:
            raise HTTPException(409, "Speech was canceled")
        return Response(audio, media_type="audio/wav" if audio.startswith(b"RIFF") else "audio/mpeg", headers={"Cache-Control": "no-store"})

    def mic_testing(self):
        return bool(self._test_id and self.test["kind"] == "microphone" and self.clock() < self._mic_until)

    def browser_test(self):
        return bool(self._test_id and self.speaker_output == "browser"
                    and self.test["kind"] in ("tone", "voice") and self.test["status"] == "running")

    async def test_api(self, request: Request):
        data = await body(request)
        kind = data.get("kind")
        if kind not in ("tone", "voice", "microphone"):
            raise HTTPException(400, "Choose tone, voice, or microphone")
        if self.running or self.busy:
            raise HTTPException(409, "Stop the activity or test and wait for pending work first")
        if kind == "microphone":
            if not self.online("mic"):
                raise HTTPException(409, "Join a phone microphone or click Use this microphone first")
            context = None
        else:
            if not self.speaker_ready():
                raise HTTPException(409, "Click Use this computer's speaker first, or join a paired speaker player")
            if kind == "voice" and not (self.audio.elevenlabs and self.audio.voice_id):
                raise HTTPException(409, "Save the ElevenLabs key and voice ID first")
            context = self.acquire(data.get("control_id"), data.get("control_epoch")) if self.speaker_output == "go2" else None
        if context is None and self.audio_acquire:
            context = self.audio_acquire(data.get("control_id"), data.get("control_epoch"))
        test_id = self._test_id = secrets.token_hex(16)
        self.test = {"kind": kind, "status": "running", "message": "Listening for 20 seconds…" if kind == "microphone" else "Preparing speaker test…"}
        self._mic_until = self.clock() + 20 if kind == "microphone" else 0
        self._test_task = asyncio.create_task(self.run_test(test_id, kind, context))
        return self.status()

    async def run_test(self, test_id, kind, context):
        def check():
            if self._test_id != test_id:
                raise HTTPException(409, "Test stopped")
            if context is not None:
                if (kind == "microphone" or self.speaker_output == "browser") and self.audio_check:
                    self.audio_check(context)
                else:
                    self.check_context(context)
        try:
            check()
            if kind == "microphone":
                while self.mic_testing():
                    check()
                    if not self.online("mic"):
                        raise HTTPException(409, "Microphone disconnected")
                    await asyncio.sleep(0.1)
                check()
                message = "Microphone test complete. " + ("Heard: " + self.test["transcript"] if self.test.get("transcript") else "No transcript received; check the microphone and Deepgram key.")
            elif self.speaker_output == "browser":
                self._test_playback = asyncio.Event()
                self.speech = {"id": secrets.token_hex(12), "kind": kind, "status": "queued",
                    "text": "Test tone" if kind == "tone" else "Hello! I am Buddy. My voice is playing through your selected speaker. Let's build three blocks together!"}
                deadline = self.clock() + self.SPEECH_TIMEOUT
                while not self._test_playback.is_set():
                    check()
                    if not self.online("speaker"):
                        raise HTTPException(409, "Speaker disconnected; enable it and retry")
                    if self.clock() >= deadline:
                        raise HTTPException(409, "Speaker test timed out; enable browser audio and retry")
                    await asyncio.sleep(0.05)
                check()
                message = "Speaker finished the test. If silent, check your Mac sound output and browser tab mute setting."
            else:
                audio = None if kind == "tone" else await asyncio.to_thread(self.audio.speak, "Hello! I am Buddy. My voice is coming from the robot's built-in speaker. Let's build three blocks together!")
                check()
                await self.speaker.play(audio, check, tone=kind == "tone")
                check()
                message = "Audio sent to Go2. If you heard it, the speaker test passed. If silent, check the robot's model and volume in the Unitree app."
            self.test.update(status="complete", message=message)
        except Exception as exc:
            if self._test_id == test_id:
                self.test.update(status="error", message=str(exc.detail) if isinstance(exc, HTTPException) else "Component test failed; check its connection and credentials")
        finally:
            if self._test_id == test_id:
                self._test_id = ""
                self._mic_until = 0
                if self.speaker_output == "browser" and kind in ("tone", "voice"):
                    self.speech = None

    async def close(self):
        self.cancel("Server shutting down")
        for task in (self._task, self._gesture_task, self._audio_job, self._speech_task, self._test_task):
            if task:
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await task
