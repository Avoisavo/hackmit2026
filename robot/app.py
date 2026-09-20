import asyncio
import contextlib
import html
import io
import json
import math
import os
import secrets
import time
from contextlib import asynccontextmanager
from itertools import count
from ipaddress import IPv4Address
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from unitree_webrtc_connect import unitree_auth
from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD, SPORT_CMD_MCF

if __package__:
    from .box_service import BoxService
    from .vision_service import VisionService
else:
    from box_service import BoxService
    from vision_service import VisionService


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


ROBOT_IP = os.getenv("ROBOT_IP", "10.254.159.2")
TOKEN = secrets.token_urlsafe(32)
CAMERA_WIDTH = 960
CAMERA_FPS = 15
SETTLE = 3.0  # seconds a posture change gets before the next command (dimOS uses 3)
SPORT_REPLY_TIMEOUT = 10
TRICK_REPLY_GRACE = 5
request_ids = count(secrets.randbelow(1 << 30) + 1)

# Posture buttons. These api_ids are identical in both motion modes.
POSTURES = {"stand": "StandUp", "balance": "BalanceStand", "lie": "StandDown"}

# Tricks: name -> (SPORT_CMD key in "normal" mode, SPORT_CMD_MCF key in ai/mcf
# mode, takes an on/off flag). Flagged commands are poses the robot holds
# until sent {"data": false}; the others are one-shot. Flag convention from
# unitree_sdk2's SportClient (HandStand/WalkUpright/Pose send {"data": flag})
# and dimOS (Standup 1050 with {"data": True}). None: no such move in that mode.
ACTIONS = {
    "hello": ("Hello", "Hello", False),
    "stretch": ("Stretch", "Stretch", False),
    "sit": ("Sit", "Sit", False),
    "rise_sit": ("RiseSit", "RiseSit", False),
    "heart": ("FingerHeart", "Heart", False),
    "content": ("Content", "Content", False),
    "scrape": ("Scrape", "Scrape", False),
    "wiggle_hips": ("WiggleHips", None, False),
    "dance1": ("Dance1", "Dance1", False),
    "dance2": ("Dance2", "Dance2", False),
    "hind_stand": ("Standup", "BackStand", True),
    "handstand": ("Handstand", "HandStand", True),
    "front_jump": ("FrontJump", "FrontJump", False),
    "front_pounce": ("FrontPounce", "FrontPounce", False),
    "front_flip": ("FrontFlip", "FrontFlip", False),
    "back_flip": ("BackFlip", "BackFlip", False),
    "left_flip": ("LeftFlip", "LeftFlip", False),
    "right_flip": ("RightFlip", None, False),
    "recovery": ("RecoveryStand", "RecoveryStand", False),
    "damp": ("Damp", "Damp", False),
}
MOTION_MODES = ("normal", "ai", "mcf")

# What the robot is left in after an accepted command. Everything else
# (tricks, flips, dances) ends standing. Held poses are handled separately.
STANCE_AFTER = {
    "StandUp": "standing",
    "RecoveryStand": "standing",
    "RiseSit": "after_trick",   # walkable only after RecoveryStand, like a trick
    "BalanceStand": "balanced",
    "StandDown": "lying",
    "Sit": "sitting",
    "Damp": "damped",
}
HELD_POSES = {"Standup": "hind_stand", "BackStand": "hind_stand",
              "Handstand": "handstand", "HandStand": "handstand"}

# How to get back to standing from a stance the robot cannot act from:
# (command name, on flag). Runs automatically before any other command.
# After a one-shot trick the controller is left in a locked stand where the
# joystick only tilts the body; RecoveryStand puts it back into a stand the
# joystick can walk from (observed on this robot).
RECOVERY = {
    "sitting": ("rise_sit", True),
    "lying": ("stand", True),
    "damped": ("stand", True),
    "unknown": ("stand", True),
    "after_trick": ("recovery", True),
    "hind_stand": ("hind_stand", False),
    "handstand": ("handstand", False),
}
# Commands that skip the usual pose-exit sequence (RiseSit / StandUp / end
# a held pose). run_command still requires RecoveryStand before the action.
DIRECT = {"rise_sit", "recovery", "damp"}

# Every trick ends with an automatic RecoveryStand once it has had this many
# seconds to finish, followed by BalanceStand and enabling movement.
# Held poses are held this long, then ended, then recovered. Sit and
# Damp leave through their own exit (RiseSit / StandUp) before RecoveryStand.
AUTO_RECOVER_AFTER = {
    "hello": 5, "stretch": 8, "heart": 5, "content": 5, "scrape": 5,
    "wiggle_hips": 6, "dance1": 15, "dance2": 20,
    "front_jump": 4, "front_pounce": 4,
    "front_flip": 5, "back_flip": 5, "left_flip": 5, "right_flip": 5,
    "sit": 5, "rise_sit": 3, "damp": 4,
    "hind_stand": 6, "handstand": 6,
}
ARM_WAIT = 60  # includes the trick, recovery pauses and robot replies

# Status codes the robot puts in reply.data.header.status.code
# (unitree_sdk2py rpc/internal.py and go2/sport/sport_api.py).
STATUS_TEXT = {
    0: "ok",
    3001: "unknown error",
    3102: "client send error",
    3103: "API not registered",
    3104: "request timed out inside the robot",
    3105: "response mismatch",
    3106: "client data error",
    3107: "lease invalid",
    3201: "server send error",
    3202: "robot refused (internal error: usually not allowed from the "
          "current posture, gait or mode)",
    3203: "not implemented by the active motion controller (try the other "
          "motion mode)",
    3204: "invalid parameters for this command",
    3205: "lease denied",
    3206: "lease does not exist",
    3207: "lease already exists",
    4201: "sport service timed out",
    4202: "sport service not initialised",
}

robot = None
armed = False
stance = "unknown"  # see STANCE_AFTER / RECOVERY
recovery_needed = True  # recover once before driving; posture/actions invalidate it
last_input = 0.0
desired = (0.0, 0.0, 0.0)
controller = None
busy = False
last_error = ""
motion_mode = ""
latest_jpeg = b""
frame_at = 0.0
camera_session = 0
action_lock = asyncio.Lock()
recovery_task = None  # scheduled automatic recovery after a trick
command_seq = 0       # bumps on every accepted sport reply
stop_epoch = 0        # prevents an interrupted operation from enabling movement


class ConnectOptions(BaseModel):
    ip: IPv4Address


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


def disarm():
    global armed, desired
    armed = False
    desired = (0.0, 0.0, 0.0)
    send_velocity()


def stop():
    global stop_epoch
    stop_epoch += 1
    cancel_scheduled_recovery()
    disarm()


def check_not_stopped(epoch):
    if epoch != stop_epoch or not connected():
        raise HTTPException(409, "Operation stopped; movement remains disabled")


def recovering():
    return recovery_task is not None and not recovery_task.done()


async def watchdog():
    global last_error
    while True:
        try:
            # Missing browser heartbeats disarm movement.
            if not connected() or (
                (armed or recovering()) and time.monotonic() - last_input > 0.3
            ):
                stop()
            else:
                send_velocity(*(desired if armed else (0, 0, 0)))
        except Exception as exc:
            last_error = str(exc)
            stop()
        await asyncio.sleep(0.05)


async def disconnect():
    global robot, motion_mode, latest_jpeg, frame_at, camera_session, stance, recovery_needed
    cancel_scheduled_recovery()
    stop()
    camera_session += 1
    vision.invalidate_camera()
    boxes.invalidate_camera()
    old, robot = robot, None
    motion_mode = ""
    latest_jpeg = b""
    frame_at = 0.0
    stance = "unknown"
    recovery_needed = True
    if old:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(old.disconnect(), timeout=5)


async def request(topic, options, timeout=5):
    # SDK 2.2.0 leaves cancelled futures in its reply registry. A late reply
    # then calls set_result() on a cancelled future and raises InvalidStateError.
    # Keep the SDK task alive until we remove our uniquely identified callback;
    # only then cancel it. This also handles STOP cancelling a recovery request.
    pub_sub = robot.datachannel.pub_sub
    resolver = pub_sub.future_resolver
    request_id = next(request_ids)
    pending = asyncio.create_task(
        pub_sub.publish_request_new(topic, {**options, "id": request_id})
    )
    try:
        return await asyncio.wait_for(asyncio.shield(pending), timeout=timeout)
    finally:
        resolver.pending_callbacks.pop(request_id, None)
        resolver.chunk_data_storage.pop(request_id, None)
        if not pending.done():
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending


def reply_status(reply):
    try:
        return reply["data"]["header"]["status"]["code"]
    except (KeyError, TypeError):
        return None


def status_text(code):
    if code is None:
        return "no status code in reply"
    return STATUS_TEXT.get(code, f"unknown status {code}")


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


def resolve(name, on=True):
    """Map a posture/action name to (api_id, key, parameter) for the
    active motion mode. Raises 404/409 like the endpoints used to."""
    if name in POSTURES:
        key = POSTURES[name]
        return SPORT_CMD[key], key, None
    if name not in ACTIONS:
        raise HTTPException(404, "Unknown action")
    normal_key, mcf_key, flag = ACTIONS[name]
    if motion_mode in ("", "normal"):
        key, table = normal_key, SPORT_CMD
    else:
        key, table = mcf_key, SPORT_CMD_MCF
    if key is None or key not in table:
        other = "normal" if motion_mode not in ("", "normal") else "ai"
        raise HTTPException(
            409,
            f"{name} is not in the {motion_mode or 'normal'} command table. "
            f"Lie the robot down and click 'Switch to {other.capitalize()}' "
            "to use it.",
        )
    return table[key], key, ({"data": on} if flag else None)


def note_stance(key, parameter, code):
    global stance, command_seq, recovery_needed
    if code != 0:
        return
    command_seq += 1
    if key in HELD_POSES:
        on = bool(parameter and parameter.get("data"))
        stance = HELD_POSES[key] if on else "after_trick"
    else:
        stance = STANCE_AFTER.get(key, "after_trick")
    if key == "RecoveryStand":
        recovery_needed = False
    elif key != "BalanceStand":
        # A posture or trick changes the recovered stance. Plain joystick
        # input and STOP do not: repeated drive keys can reuse the recovery.
        recovery_needed = True


def cancel_scheduled_recovery():
    global recovery_task
    if recovery_task and not recovery_task.done():
        recovery_task.cancel()
    recovery_task = None


def schedule_recovery(delay):
    global recovery_task
    cancel_scheduled_recovery()
    recovery_task = asyncio.create_task(
        auto_recover(delay, command_seq, stop_epoch, controller)
    )


async def auto_recover(delay, seq, epoch, owner):
    # Fires once a trick has had time to finish: leaves the pose the robot is
    # in (RiseSit / StandUp / end a held pose) and always ends with
    # RecoveryStand, BalanceStand, then movement enabled. A stop or newer
    # command cancels the sequence; only the original live dashboard can drive.
    global busy, last_error, armed
    await asyncio.sleep(delay)
    if (seq != command_seq or epoch != stop_epoch or not connected()
            or action_lock.locked()):
        return
    async with action_lock:
        busy = True
        disarm()
        try:
            steps = await recover_to_standing("automatic recovery", epoch)
            if not any(s["command"].startswith("RecoveryStand") for s in steps):
                await recovery_stand("automatic recovery", epoch)
            check_not_stopped(epoch)
            await prepare_stance(epoch)
            check_not_stopped(epoch)
            if (owner is not None and controller is owner
                    and time.monotonic() - last_input <= 0.3):
                armed = True
        except HTTPException as exc:
            last_error = str(exc.detail)
        finally:
            busy = False


async def send_sport(key, api_id, parameter, label, timeout=None):
    """One SPORT_MOD request. Caller holds action_lock. Returns the result
    dict; raises 504 on no reply."""
    global last_error, stance, recovery_needed
    if timeout is None:
        timeout = SPORT_REPLY_TIMEOUT
    options = {"api_id": api_id}
    if parameter is not None:
        options["parameter"] = parameter
    try:
        reply = await request(RTC_TOPIC["SPORT_MOD"], options, timeout=timeout)
    except asyncio.TimeoutError:
        # Keep the session so the operator can still send Lie down / STOP.
        # The robot may or may not have moved, so forget what we knew.
        stance = "unknown"
        recovery_needed = True
        last_error = (
            f"{label}: no reply within {timeout:g}s. Movement stays disabled. "
            "Once the robot has finished, press a drive key or Enable movement "
            "to recover; the trick will not be repeated."
        )
        raise HTTPException(504, last_error)
    except asyncio.CancelledError:
        stance = "unknown"
        recovery_needed = True
        raise
    code = reply_status(reply)
    if code is None:
        stance = "unknown"
        recovery_needed = True
    note_stance(key, parameter, code)
    return {
        "command": label,
        "api_id": api_id,
        "parameter": parameter,
        "status_code": code,
        "status_text": status_text(code),
        "reply": reply,
    }


async def recovery_stand(for_label, epoch):
    global last_error
    check_not_stopped(epoch)
    api_id, key, parameter = resolve("recovery")
    step = await send_sport(
        key, api_id, parameter, f"RecoveryStand ({for_label})"
    )
    if step["status_code"] != 0:
        last_error = f"RecoveryStand refused: {step['status_text']}"
        raise HTTPException(409, last_error)
    await asyncio.sleep(SETTLE)
    check_not_stopped(epoch)
    return step


async def recover_to_standing(for_label, epoch):
    """If the robot is sitting, lying, damped or in a held pose, bring it
    back to standing first (Rise from sit / Stand up / end the pose), with a
    settle pause. Caller holds action_lock. Returns the steps taken."""
    global last_error
    steps = []
    for _ in range(3):
        check_not_stopped(epoch)
        if stance not in RECOVERY:
            break
        name, on = RECOVERY[stance]
        api_id, key, parameter = resolve(name, on)
        step = await send_sport(
            key, api_id, parameter, f"{key} (preparing for {for_label})"
        )
        steps.append(step)
        if step["status_code"] != 0:
            last_error = (
                f"{key} refused before {for_label}: {step['status_text']}"
            )
            raise HTTPException(409, last_error)
        await asyncio.sleep(SETTLE)
    check_not_stopped(epoch)
    return steps


async def run_command(name, on=True):
    """Recover before each posture/trick, then execute only after success."""
    global busy, last_error
    api_id, key, parameter = resolve(name, on)
    label = key if parameter is None else f"{key} {'on' if on else 'off'}"
    if not connected():
        raise HTTPException(409, "Robot disconnected")
    if action_lock.locked():
        raise HTTPException(409, "Another operation is running")

    async with action_lock:
        busy = True
        cancel_scheduled_recovery()
        stop()
        epoch = stop_epoch
        try:
            steps = []
            if name not in DIRECT and on:
                steps = await recover_to_standing(label, epoch)
            # Leaving a held pose / after-trick stance may already have sent
            # RecoveryStand. Do not send it twice for the same action, or
            # prepend RecoveryStand to an explicit RecoveryStand request.
            if name != "recovery" and not any(
                step["api_id"] == resolve("recovery")[0] for step in steps
            ):
                steps.append(await recovery_stand(label, epoch))
            check_not_stopped(epoch)
            duration = AUTO_RECOVER_AFTER.get(name, 0) if on else SETTLE
            timeout = max(SPORT_REPLY_TIMEOUT, duration + TRICK_REPLY_GRACE)
            sent_at = time.monotonic()
            result = await send_sport(key, api_id, parameter, label, timeout=timeout)
            last_error = ""
            after = None
            if (name in AUTO_RECOVER_AFTER and result["status_code"] == 0
                    and epoch == stop_epoch):
                # Ending a held pose early still gets its RecoveryStand.
                # A reply may arrive after the trick finishes. Count from the
                # send time rather than waiting for the entire trick twice.
                delay = max(0, duration - (time.monotonic() - sent_at))
                schedule_recovery(delay)
                after = (f"RecoveryStand in {delay:.1f}s, then BalanceStand "
                         "and movement enabled")
            result.update(
                mode=motion_mode or "unknown",
                stance=stance,
                before=steps,
                after=after,
                note="Reply received; verify the robot actually moved",
            )
            return result
        finally:
            busy = False


async def prepare_stance(epoch):
    # Recover once, then balance. Joystick input and ordinary disarming do
    # not invalidate recovery, so subsequent drive keys need no sport RPCs.
    # From Sit / a held pose, leave that pose first. Caller holds action_lock.
    global last_error
    disarm()
    steps = await recover_to_standing("driving", epoch)
    if recovery_needed:
        steps.append(await recovery_stand("driving", epoch))
    if stance != "balanced":
        step = await send_sport(
            "BalanceStand", SPORT_CMD["BalanceStand"], None, "BalanceStand"
        )
        steps.append(step)
        if step["status_code"] != 0:
            last_error = f"BalanceStand refused: {step['status_text']}"
            raise HTTPException(409, last_error)
    check_not_stopped(epoch)
    last_error = ""
    return steps


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
    source_robot, source_session = robot, camera_session
    next_at = 0.0
    while True:
        try:
            frame = await track.recv()
        except Exception:
            return
        if robot is not source_robot or camera_session != source_session:
            return
        now = time.monotonic()
        if now < next_at:
            continue  # drop frames down to CAMERA_FPS
        next_at = now + 1 / CAMERA_FPS
        try:
            jpeg = await asyncio.to_thread(encode_jpeg, frame)
            if robot is not source_robot or camera_session != source_session:
                return
            latest_jpeg = jpeg
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
    await vision.close()
    await boxes.close()


app = FastAPI(lifespan=lifespan)
boxes = BoxService(lambda: (latest_jpeg, frame_at, camera_session), connected)
vision = VisionService(lambda: (latest_jpeg, frame_at, camera_session), connected,
                       box_status=boxes.status)
app.include_router(vision.router)
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
    page = Path(__file__).with_name("index.html").read_text()
    page = page.replace("__TOKEN__", TOKEN).replace("__ROBOT_IP__", html.escape(ROBOT_IP))
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@app.get("/vision", response_class=HTMLResponse)
async def vision_page():
    page = Path(__file__).with_name("vision.html").read_text()
    return HTMLResponse(page.replace("__TOKEN__", TOKEN),
                        headers={"Cache-Control": "no-store"})


@app.get("/api/status")
async def status():
    return {
        "ip": ROBOT_IP,
        "connected": connected(),
        "armed": armed,
        "busy": busy,
        "recovering": recovering(),
        "mode": motion_mode,
        "stance": stance,
        "camera": bool(latest_jpeg) and time.monotonic() - frame_at < 2,
        "error": last_error,
        "boxes": boxes.status(),
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


@app.get("/camera.boxes.mjpeg")
async def camera_boxes(token: str = ""):
    if token != TOKEN:
        raise HTTPException(403, "Unauthorized")
    return StreamingResponse(
        boxes.frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/connect")
async def connect(options: ConnectOptions | None = None):
    global robot, busy, last_error, ROBOT_IP
    if action_lock.locked():
        raise HTTPException(409, "Another operation is running")
    async with action_lock:
        if options is not None:
            ROBOT_IP = str(options.ip)
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
            return {"connected": True, "ip": ROBOT_IP, "mode": motion_mode}
        except Exception as exc:
            reason = str(exc) or type(exc).__name__
            last_error = (
                f"Could not connect to {ROBOT_IP}: {reason}. "
                "Check the latest LAN discovery IP and that the Mac and robot "
                "are on the same Wi-Fi. Close other robot clients before retrying."
            )
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
    global armed, last_input, busy
    if not connected() or controller is None:
        raise HTTPException(409, "Connect robot and dashboard first")
    epoch, owner = stop_epoch, controller
    # Wait for the whole trick and recovery, including the scheduled delay.
    # Never cancel that delay or recover in the middle of a trick.
    try:
        async with asyncio.timeout(ARM_WAIT):
            while True:
                if recovering():
                    pending = recovery_task
                    try:
                        await asyncio.shield(pending)
                    except asyncio.CancelledError:
                        if pending.cancelled():
                            raise HTTPException(409, "Automatic recovery stopped")
                        raise
                    check_not_stopped(epoch)
                    if not armed:
                        raise HTTPException(
                            409, last_error or "Automatic recovery did not enable movement"
                        )
                async with action_lock:
                    check_not_stopped(epoch)
                    if controller is not owner:
                        raise HTTPException(409, "Dashboard disconnected")
                    # A command may have scheduled recovery while we waited.
                    if recovering():
                        continue
                    busy = True
                    try:
                        steps = []
                        if stance != "balanced" or recovery_needed:
                            steps = await prepare_stance(epoch)
                        check_not_stopped(epoch)
                        if controller is not owner:
                            raise HTTPException(409, "Dashboard disconnected")
                        armed = True
                        last_input = time.monotonic()
                        return {"armed": True, "stance": stance,
                                "before": steps or "already in balance stand"}
                    finally:
                        busy = False
    except asyncio.TimeoutError:
        raise HTTPException(409, "Another operation is still running")


@app.post("/api/posture/{name}")
async def posture(name: str):
    if name not in POSTURES:
        raise HTTPException(404, "Unknown posture")
    return await run_command(name)


@app.post("/api/action/{name}")
async def action(name: str, on: bool = True):
    return await run_command(name, on)


@app.post("/api/mode/{name}")
async def set_mode(name: str):
    # Motion switcher api 1002 = SelectMode. The controller swap takes a few
    # seconds; dimOS waits 5 s after the same call.
    global busy, last_error, stance, recovery_needed
    if name not in MOTION_MODES:
        raise HTTPException(404, "Unknown motion mode")
    if not connected():
        raise HTTPException(409, "Robot disconnected")
    if action_lock.locked():
        raise HTTPException(409, "Another operation is running")

    async with action_lock:
        busy = True
        cancel_scheduled_recovery()
        stance = "unknown"
        recovery_needed = True
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
            desired = tuple(max(-1.0, min(1.0, v)) for v in values)
            last_input = time.monotonic()
            if not armed or busy:
                desired = (0, 0, 0)
    except Exception:
        pass
    finally:
        stop()
        controller = None
