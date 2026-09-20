"""Send bounded audio on the robot's existing WebRTC audio transceiver.

No second robot connection, local sound output, robot file uploads, or shell
codec process. STOP replaces queued samples with silence immediately. A finished
stream confirms transmission only; firmware offers no audibility acknowledgement.
"""
import asyncio
import io
import time
from collections import deque
from fractions import Fraction

import av
import numpy as np
from aiortc import AudioStreamTrack
from aiortc.mediastreams import MediaStreamError
from fastapi import HTTPException

RATE = 48000
SAMPLES = 960  # Opus / 20 ms
MAX_SECONDS = 30


def decode_audio(data):
    if not isinstance(data, bytes) or not 1 <= len(data) <= 8_000_000:
        raise ValueError("Invalid speech audio")
    parts, length = [], 0
    resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
    with av.open(io.BytesIO(data)) as container:
        if not container.streams.audio:
            raise ValueError("No audio stream")
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                values = converted.to_ndarray().reshape(-1).copy()
                length += len(values)
                if length > RATE * MAX_SECONDS:
                    raise ValueError("Speech exceeds 30 seconds")
                parts.append(values)
        for converted in resampler.resample(None):
            parts.append(converted.to_ndarray().reshape(-1).copy())
    pcm = np.concatenate(parts) if parts else np.array([], dtype=np.int16)
    if not 0 < len(pcm) <= RATE * MAX_SECONDS:
        raise ValueError("Speech is empty or too long")
    # Leave headroom; the robot's system volume is still controlled by Unitree.
    return (pcm.astype(np.float32) * 0.65).astype(np.int16)


def test_tone():
    seconds = 0.65
    t = np.arange(int(RATE * seconds)) / RATE
    envelope = np.minimum(1, np.minimum(t / 0.03, (seconds - t) / 0.06))
    return (np.sin(2 * np.pi * 660 * t) * envelope * 5000).astype(np.int16)


class SpeakerTrack(AudioStreamTrack):
    def __init__(self):
        super().__init__()
        self.queue = deque()
        self.samples = 0
        self.next_at = None
        self.drained = asyncio.Event()
        self.drained.set()

    def clear(self):
        self.queue.clear()
        self.drained.set()

    def enqueue(self, pcm):
        self.clear()
        for start in range(0, len(pcm), SAMPLES):
            chunk = np.zeros(SAMPLES, dtype=np.int16)
            values = pcm[start:start + SAMPLES]
            chunk[:len(values)] = values
            self.queue.append(chunk)
        self.drained.clear()

    async def recv(self):
        if self.readyState != "live":
            raise MediaStreamError
        loop = asyncio.get_running_loop()
        now = loop.time()
        self.next_at = max(self.next_at or now, now - 0.02)
        await asyncio.sleep(max(0, self.next_at - now))
        self.next_at += 0.02
        if self.readyState != "live":
            raise MediaStreamError
        pcm = self.queue.popleft() if self.queue else np.zeros(SAMPLES, dtype=np.int16)
        frame = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = RATE
        frame.pts = self.samples
        frame.time_base = Fraction(1, RATE)
        self.samples += SAMPLES
        if not self.queue:
            self.drained.set()
        return frame

    def stop(self):
        self.clear()
        super().stop()


class Go2Speaker:
    def __init__(self, get_robot, connected):
        self.get_robot, self.connected = get_robot, connected
        self.robot = None
        self.track = None
        self.generation = 0
        self.playing = False
        self.message = "Connect Go2 to enable its built-in speaker."

    def ready(self):
        return bool(self.connected() and self.robot is self.get_robot() and self.track
                    and self.track.readyState == "live")

    def status(self):
        return {"output": "go2", "ready": self.ready(), "playing": self.playing,
                "message": self.message, "audibility_verified": False}

    def attach(self, robot):
        self.detach()
        # The SDK already negotiated a sendrecv audio transceiver. Reuse it;
        # creating a second one after negotiation would require another SDP.
        transceiver = next((t for t in robot.pc.getTransceivers() if t.kind == "audio"), None)
        if transceiver is None or transceiver.currentDirection not in ("sendrecv", "sendonly"):
            raise RuntimeError("Go2 did not negotiate an outgoing audio channel")
        self.track = SpeakerTrack()
        transceiver.sender.replaceTrack(self.track)
        self.robot = robot
        self.message = "Go2 audio channel ready. Play a test tone to check the speaker."

    def stop(self):
        self.generation += 1
        if self.track:
            self.track.clear()
        if self.playing:
            self.message = "Audio stopped."
        self.playing = False

    def detach(self):
        self.stop()
        if self.track:
            self.track.stop()
        self.track, self.robot = None, None

    async def play(self, audio, check, *, tone=False):
        if self.playing:
            raise HTTPException(409, "The robot speaker is already playing")
        if not self.ready():
            raise HTTPException(409, "Connect a Go2 with a built-in speaker first")
        generation, track = self.generation, self.track
        self.playing = True
        try:
            check()
            pcm = test_tone() if tone else await asyncio.to_thread(decode_audio, audio)
            check()
            if generation != self.generation or not self.ready() or track is not self.track:
                raise HTTPException(409, "Audio was stopped or the robot connection changed")
            track.enqueue(pcm)
            self.message = "Streaming to Go2's built-in speaker…"
            deadline = time.monotonic() + len(pcm) / RATE + 3
            while not track.drained.is_set():
                check()
                if generation != self.generation or not self.ready():
                    raise HTTPException(409, "Robot audio interrupted")
                if time.monotonic() >= deadline:
                    raise HTTPException(504, "Go2 audio sender stalled; reconnect and test again")
                await asyncio.sleep(0.02)
            # Small drain interval before enabling the microphone again.
            for _ in range(10):
                check()
                if generation != self.generation:
                    raise HTTPException(409, "Robot audio interrupted")
                await asyncio.sleep(0.02)
            self.message = "Audio stream sent to Go2. Hearing the sound confirms playback."
            return {"sent": True, "output": "go2", "seconds": round(len(pcm) / RATE, 2),
                    "audibility_verified": False}
        finally:
            if track is self.track:
                track.clear()
            self.playing = False
