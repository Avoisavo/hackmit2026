import asyncio
import contextlib
import io
import json
import math
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from unitree_webrtc_connect import unitree_auth
from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD, SPORT_CMD_MCF


# The library runs the LAN signaling handshake with blocking sockets on the
# event loop and issues its HTTP requests without a timeout. Left as is, a
# robot that accepts TCP but never answers freezes the watchdog, STOP and
# the 40 s connect guard for the whole process. Bound the requests and run
# the handshake in a worker thread instead.
def _bounded_local_request(path, body=None, headers=None):
    try:
        response = requests.post(
            url=path, data=body, headers=headers, timeout=(3, 10)
        )
        response.raise_for_status()
        return response if response.status_code == 200 else None
    except requests.exceptions.RequestException as exc:
        print(f"Local signaling request failed: {exc}")
        return None


unitree_auth.make_local_request = _bounded_local_request


class Go2Connection(UnitreeWebRTCConnection):
    async def get_answer_from_local_peer(self, pc, ip):
        offer = pc.localDescription
        payload = json.dumps(
            {
                "id": "STA_localNetwork"
                if self.connectionMethod == WebRTCConnectionMethod.LocalSTA
                else "",
                "sdp": offer.sdp,
                "type": offer.type,
                "token": self.token,
            }
        )
        return await asyncio.to_thread(
            unitree_auth.send_sdp_to_local_peer,
            ip,
            payload,
            aes_128_key=self.aes_128_key,
        )


ROBOT_IP = os.getenv("ROBOT_IP", "172.20.10.4")
TOKEN = secrets.token_urlsafe(32)
CAMERA_WIDTH = 960
CAMERA_FPS = 15

# Posture buttons. These api_ids are identical in both motion modes.
POSTURES = {"stand": "StandUp", "balance": "BalanceStand", "lie": "StandDown"}

# Tricks: name -> (SPORT_CMD key in "normal" mode, SPORT_CMD_MCF key in ai/mcf
# mode). None means the robot has no such move in that mode.
ACTIONS = {
    "hello": ("Hello", "Hello"),
    "stretch": ("Stretch", "Stretch"),
    "sit": ("Sit", "Sit"),
    "rise_sit": ("RiseSit", "RiseSit"),
    "heart": ("FingerHeart", "Heart"),
    "content": ("Content", "Content"),
    "scrape": ("Scrape", "Scrape"),
    "wiggle_hips": ("WiggleHips", None),
    "dance1": ("Dance1", "Dance1"),
    "dance2": ("Dance2", "Dance2"),
    "hind_stand": ("Standup", "BackStand"),
    "handstand": ("Handstand", "HandStand"),
    "front_jump": ("FrontJump", "FrontJump"),
    "front_pounce": ("FrontPounce", "FrontPounce"),
    "front_flip": ("FrontFlip", "FrontFlip"),
    "back_flip": ("BackFlip", "BackFlip"),
    "left_flip": ("LeftFlip", "LeftFlip"),
    "right_flip": ("RightFlip", None),
    "recovery": ("RecoveryStand", "RecoveryStand"),
    "damp": ("Damp", "Damp"),
}
MOTION_MODES = ("normal", "ai", "mcf")

robot = None
armed = False
last_input = 0.0
desired = (0.0, 0.0, 0.0)
controller = None
busy = False
last_error = ""
motion_mode = ""
latest_jpeg = b""
frame_at = 0.0
action_lock = asyncio.Lock()


def same_origin(ws: WebSocket) -> bool:
    # The dashboard may run on any local port; the socket must come from the
    # page this server served (TrustedHostMiddleware already pins the host).
    host = ws.headers.get("host", "")
    return bool(host) and ws.headers.get("origin") == f"http://{host}"


def connected():
    try:
        # data_channel_opened flips only after the robot's validation
        # handshake; aiortc's readyState goes "open" earlier than that.
        return (
            robot is not None
            and robot.pc.connectionState == "connected"
            and robot.datachannel.data_channel_opened
            and robot.datachannel.pub_sub.channel.readyState == "open"
        )
    except AttributeError:
        return False


def send_velocity(forward=0.0, left=0.0, turn=0.0):
    # Matches dimOS's WebRTC joystick mapping.
    # These are joystick inputs, NOT calibrated metres/second.
    if connected():
        robot.datachannel.pub_sub.publish_without_callback(
            RTC_TOPIC["WIRELESS_CONTROLLER"],
            data={"lx": -left, "ly": forward, "rx": -turn, "ry": 0},
        )


def stop():
    global armed, desired, last_input
    armed = False
    desired = (0.0, 0.0, 0.0)
    last_input = 0.0
    send_velocity()


async def watchdog():
    global last_error
    while True:
        try:
            # Missing browser heartbeats disarm movement.
            if not connected() or (
                armed and time.monotonic() - last_input > 0.3
            ):
                stop()
            else:
                send_velocity(*(desired if armed else (0, 0, 0)))
        except Exception as exc:
            last_error = str(exc)
            stop()
        await asyncio.sleep(0.05)


async def disconnect():
    global robot, motion_mode, latest_jpeg
    stop()
    old, robot = robot, None
    motion_mode = ""
    latest_jpeg = b""
    if old:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(old.disconnect(), timeout=5)


async def request(topic, options, timeout=5):
    return await asyncio.wait_for(
        robot.datachannel.pub_sub.publish_request_new(topic, options),
        timeout=timeout,
    )


def reply_status(reply):
    try:
        return reply["data"]["header"]["status"]["code"]
    except (KeyError, TypeError):
        return None


async def check_mode():
    # Motion switcher api 1001 = CheckMode; reply carries {"name": <mode>}.
    global motion_mode
    try:
        reply = await request(RTC_TOPIC["MOTION_SWITCHER"], {"api_id": 1001})
        motion_mode = json.loads(reply["data"]["data"]).get("name") or ""
    except Exception as exc:
        motion_mode = ""
        print(f"Motion mode check failed: {exc}")
    return motion_mode


def sport_id(name):
    normal_key, mcf_key = ACTIONS[name]
    if motion_mode in ("", "normal"):
        key, table = normal_key, SPORT_CMD
    else:
        key, table = mcf_key, SPORT_CMD_MCF
    if key is None or key not in table:
        return None, None
    return table[key], key


def encode_jpeg(frame):
    width = min(CAMERA_WIDTH, frame.width)
    height = max(2, round(frame.height * width / frame.width / 2) * 2)
    image = frame.reformat(width=width, height=height, format="rgb24").to_image()
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=70)
    return buf.getvalue()


async def read_video(track):
    # Registered with the driver's video channel; runs until the track ends.
    global latest_jpeg, frame_at
    next_at = 0.0
    while True:
        try:
            frame = await track.recv()
        except Exception:
            return
        now = time.monotonic()
        if now < next_at:
            continue  # drop frames down to CAMERA_FPS
        next_at = now + 1 / CAMERA_FPS
        try:
            latest_jpeg = await asyncio.to_thread(encode_jpeg, frame)
            frame_at = time.monotonic()
        except Exception as exc:
            print(f"Camera frame encode failed: {exc}")


async def after_connect():
    # Same order as dimOS: register the reader, then ask the robot for video.
    robot.video.add_track_callback(read_video)
    robot.video.switchVideoChannel(True)
    await check_mode()


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(watchdog())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await disconnect()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost"],
)


@app.middleware("http")
async def protect_api(request: Request, call_next):
    # Browser receives this per-run token from the local dashboard.
    if request.url.path.startswith("/api/"):
        if request.headers.get("X-Control-Token") != TOKEN:
            return JSONResponse({"detail": "Unauthorized"}, status_code=403)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
async def home():
    html = Path(__file__).with_name("index.html").read_text()
    return html.replace("__TOKEN__", TOKEN)


@app.get("/api/status")
async def status():
    return {
        "ip": ROBOT_IP,
        "connected": connected(),
        "armed": armed,
        "busy": busy,
        "mode": motion_mode,
        "camera": bool(latest_jpeg) and time.monotonic() - frame_at < 2,
        "error": last_error,
    }


@app.get("/camera.mjpeg")
async def camera(token: str = ""):
    # <img> tags cannot send headers, so this one endpoint takes the token
    # as a query parameter instead of X-Control-Token.
    if token != TOKEN:
        raise HTTPException(403, "Unauthorized")

    async def frames():
        sent_at = -1.0
        while connected():
            if latest_jpeg and frame_at != sent_at:
                sent_at = frame_at
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(latest_jpeg)).encode()
                    + b"\r\n\r\n"
                    + latest_jpeg
                    + b"\r\n"
                )
            await asyncio.sleep(0.5 / CAMERA_FPS)

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/connect")
async def connect():
    global robot, busy, last_error
    if action_lock.locked():
        raise HTTPException(409, "Another operation is running")
    async with action_lock:
        busy = True
        last_error = ""
        conn = None
        try:
            await disconnect()
            # Build locally; the watchdog only sees `robot` once validated.
            conn = Go2Connection(
                WebRTCConnectionMethod.LocalSTA,
                ip=ROBOT_IP,
                aes_128_key=os.getenv("UNITREE_AES_128_KEY"),
            )
            await asyncio.wait_for(conn.connect(), timeout=40)
            robot = conn
            if not connected():
                raise RuntimeError("WebRTC data channel did not open")
            stop()
            await after_connect()
            return {"connected": True, "mode": motion_mode}
        except Exception as exc:
            last_error = str(exc)
            robot = conn
            await disconnect()
            raise HTTPException(502, last_error or "Connection failed")
        finally:
            busy = False


@app.post("/api/disconnect")
async def disconnect_api():
    if action_lock.locked():
        raise HTTPException(409, "Another operation is running")
    async with action_lock:
        await disconnect()
    return {"connected": False}


@app.post("/api/stop")
async def stop_api():
    stop()
    return {"armed": False, "note": "Stop requested; verify physically"}


@app.post("/api/arm")
async def arm():
    global armed, last_input
    if not connected() or controller is None or busy:
        raise HTTPException(409, "Connect robot and dashboard first")
    armed = True
    last_input = time.monotonic()
    return {"armed": True}


async def sport_command(api_id, label, timeout=5):
    # Sends one SPORT_MOD request under the action lock with movement disarmed.
    global busy, last_error
    if not connected():
        raise HTTPException(409, "Robot disconnected")
    if action_lock.locked():
        raise HTTPException(409, "Another operation is running")

    async with action_lock:
        busy = True
        stop()
        try:
            reply = await request(
                RTC_TOPIC["SPORT_MOD"], {"api_id": api_id}, timeout=timeout
            )
            last_error = ""
            # An RPC reply is not proof of physical movement.
            return {
                "command": label,
                "api_id": api_id,
                "mode": motion_mode or "unknown",
                "status_code": reply_status(reply),
                "reply": reply,
                "note": "Reply received; verify the robot actually moved",
            }
        except asyncio.TimeoutError:
            # Keep the session so the operator can still send Lie down / STOP.
            last_error = (
                f"{label}: no reply within {timeout}s. Outcome unknown; "
                "check the robot before retrying."
            )
            raise HTTPException(504, last_error)
        finally:
            busy = False


@app.post("/api/posture/{name}")
async def posture(name: str):
    if name not in POSTURES:
        raise HTTPException(404, "Unknown posture")
    key = POSTURES[name]
    return await sport_command(SPORT_CMD[key], key)


@app.post("/api/action/{name}")
async def action(name: str):
    if name not in ACTIONS:
        raise HTTPException(404, "Unknown action")
    api_id, key = sport_id(name)
    if api_id is None:
        raise HTTPException(
            409, f"{name} is not available in {motion_mode or 'normal'} mode"
        )
    return await sport_command(api_id, key)


@app.post("/api/mode/{name}")
async def set_mode(name: str):
    # Motion switcher api 1002 = SelectMode. The controller swap takes a few
    # seconds; dimOS waits 5 s after the same call.
    global busy, last_error
    if name not in MOTION_MODES:
        raise HTTPException(404, "Unknown motion mode")
    if not connected():
        raise HTTPException(409, "Robot disconnected")
    if action_lock.locked():
        raise HTTPException(409, "Another operation is running")

    async with action_lock:
        busy = True
        stop()
        try:
            reply = await request(
                RTC_TOPIC["MOTION_SWITCHER"],
                {"api_id": 1002, "parameter": {"name": name}},
                timeout=10,
            )
            await asyncio.sleep(3)
            current = await check_mode()
            last_error = ""
            return {
                "requested": name,
                "mode": current or "unknown",
                "status_code": reply_status(reply),
                "reply": reply,
            }
        except asyncio.TimeoutError:
            last_error = f"Mode switch to {name}: no reply within 10s."
            raise HTTPException(504, last_error)
        finally:
            busy = False


@app.websocket("/ws/control")
async def control(ws: WebSocket):
    global controller, desired, last_input
    if not same_origin(ws) or ws.query_params.get("token") != TOKEN:
        await ws.close(code=1008)
        return

    await ws.accept()
    if controller is not None:
        await ws.close(code=1008, reason="Another dashboard owns control")
        return

    controller = ws
    stop()
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "stop":
                stop()
                continue
            if data.get("type") != "move":
                continue

            # Bound every command on the server.
            values = [float(data.get(k, 0)) for k in ("forward", "left", "turn")]
            if not all(math.isfinite(v) for v in values):
                raise ValueError("Invalid movement")
            desired = tuple(max(-0.3, min(0.3, v)) for v in values)
            last_input = time.monotonic()
            if not armed or busy:
                desired = (0, 0, 0)
    except Exception:
        pass
    finally:
        stop()
        controller = None
