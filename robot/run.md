# Go2 web dashboard

Drive a Unitree Go2 from a browser over the same WebRTC link dimOS uses.

## Before you connect

- **Stop dimOS first.** The Go2 accepts one WebRTC client at a time, so
  Ctrl+C the `dimos run unitree-go2` terminal (and close the Unitree phone
  app). If Connect fails right after that, wait about 15 s for the robot to
  drop the old peer and try again.
- Your Mac and the robot must be on the same Wi-Fi network.

## Run

```sh
source ~/dimensional-applications/.venv/bin/activate
cd ~/Developer/hackmit2026/robot
export ROBOT_IP='10.254.159.2'
python -m uvicorn app:app --host 127.0.0.1 --port 8010
```

Then open http://127.0.0.1:8010 in a browser on this Mac.

To select this copy explicitly from any terminal directory, use:

```sh
~/dimensional-applications/.venv/bin/python -m uvicorn app:app --app-dir ~/Developer/hackmit2026/robot --host 127.0.0.1 --port 8010
```

The updated controls include **Robot connection → Robot IP**, a **Show labeled
object boxes** checkbox under the camera, and an **Open camera object recognition
& counting** link. If any are missing, stop the old server and use the explicit
command above, then reload the page.

Enter the robot's latest discovered address in **Robot IP**, then click
**Connect robot**. The address can change when the Wi-Fi network changes;
you can update it in the dashboard without restarting the server. `ROBOT_IP`
sets the initial address at startup. For robot serial `B42D1000PC48I1GW`,
the latest reported address is `10.254.159.2` (previously `172.20.10.4`).

Run from this project's `robot` directory: the separate `~/Developer/mit`
copy does not pick up changes made here. If port 8010 already has that old
server running, stop it with Ctrl+C before starting this one.

The server does not reload `app.py` on its own: after any change to it,
Ctrl+C and start it again. After **every** server restart, reload the
browser tab, because the page holds a per-run session token (the page tells
you when this is needed).

Any free port works. Port 8000 on this machine is held by
`solana-test-validator`, which is why the old command failed to bind.
Everything the dashboard needs is already in that venv. On a fresh venv,
install the pinned set with `uv pip install -r requirements.txt`.

## AES key (only if Connect says the robot needs it)

Go2 firmware 1.1.15 and newer requires a per-device AES-128 key for the LAN
handshake. dimOS connected to this robot without one, so you probably don't
need it. If the dashboard reports `AesKeyRequiredError`:

```sh
unitree-fetch-aes-key --email you@example.com --device-type Go2 --sn <ROBOT_SN> --quiet
export UNITREE_AES_128_KEY='<32 hex chars from the command above>'
```

and restart the server.

## Driving

1. **Connect robot** and wait for the status line to say Connected.
2. **Hold W/S** (forward/back), **Q/E** (strafe), **A/D** (turn) or the
   on-screen buttons. The first press after connecting or after any posture
   change enables movement by itself: it leaves any sitting/held pose,
   runs Recovery stand once, waits 3 s, then sends Balance stand and drives.
   Later presses reuse that recovery, including after STOP or losing focus.
   A trick, posture change, mode switch or reconnection requires recovery
   again; automatic recovery after a trick also satisfies this requirement.
   Releasing sends zero input.
   Keyboard and direction buttons use full joystick input (±1.0 per axis).
3. **Space** or the red STOP button disarms. Posture buttons also disarm;
   the next key press re-enables. Tricks pause driving and automatically
   recover, enter Balance stand, and re-enable movement when finished.

The Stand up / Balance stand / Enable movement buttons still work if you
want to do the steps by hand.

Movement disarms automatically if the browser stops sending heartbeats for
0.3 s, when the tab loses focus, or when the WebSocket drops. Always stay
within reach of the robot's physical remote or power switch; a software
stop is not a guarantee.

## Camera, motion mode, tricks

- **Camera**: the front camera appears at the top of the page a second or
  two after Connect (MJPEG, 15 fps, 960 px wide).
- **Motion mode**: the page shows the robot's current controller
  (`normal` or `ai`/`mcf`). dimOS switches the robot to `ai` when it
  connects. The tricks below use the ID table for whichever mode is active.
  Switch modes while the robot is lying down; the swap takes a few seconds.
- **Before every action/posture**: the app runs Recovery stand and waits
  for a successful reply plus a 3 s settling pause before sending the
  requested command. A refused or timed-out recovery prevents the action.
  STOP cancels the pending action. Recovery needed to leave a previous pose
  counts toward this step, and requesting Recovery stand itself sends it once.
- **Tricks**: Hello, Stretch, Heart, Content, Scrape, Wiggle hips, Sit,
  Rise from sit, Dance 1/2, and the orange ones: Stand on hind legs,
  Handstand, Jump forward, Pounce, Front/Back/Left/Right flip, Damp (go
  limp). Tricks run after Recovery stand and every one ends with an
  automatic Recovery stand, Balance stand, and movement enabled again.
  Give the robot at least 2 m of clear, flat
  space before the orange ones. A trick that does not exist in the current
  mode (for example Wiggle hips or Right flip in `mcf` mode) returns 409
  and tells you which mode to switch to.
- **Held poses**: Stand on hind legs and Handstand are on/off commands
  (sent with `{"data": true}`); the End buttons send `{"data": false}`.
- **Robot answers**: every posture and trick shows the robot's status code
  in the yellow line. 0 is accepted. 3204 means bad parameters, 3203 means
  the active motion controller has no such command, 3202 usually means the
  move is not allowed from the current posture or gait (stand in Balance
  stand first). An accepted reply is still not proof the robot moved.
- Posture buttons disarm driving; the next key press re-enables.
- **After a trick** the controller is left in a locked stand where the
  joystick only tilts the body. The app sends Recovery stand by itself once
  the trick has had time to finish (3 to 20 s depending on the trick), then
  sends Balance stand and enables movement automatically. Sit and
  Damp leave through Rise from sit / Stand up first; hind-leg stand and
  handstand are held 6 s, then ended, then recovered. A key press during a
  trick waits for the recovery to finish, then drives while the key is held.
  STOP, loss of window focus, a tab switch, a missing dashboard heartbeat,
  or disconnection cancels the automatic sequence and keeps driving disabled.
  Failed or unconfirmed recovery commands leave movement disabled.
- **Slow replies / timeouts**: sport commands wait at least 10 s for a reply;
  longer tricks get their configured duration plus 5 s (up to 25 s). A late
  successful reply still starts recovery, without waiting the full trick
  duration a second time. If the deadline expires, the command is not retried
  and movement stays disabled. Once the robot has finished, press a drive key
  or Enable movement: it must complete Recovery stand before driving again.
  Timed-out or cancelled requests are removed from the SDK's callback registry
  so later replies cannot trigger `InvalidStateError`.
- **From Sit, lying, Damp, a hind-leg stand or a handstand**, the next key
  press or trick first brings the robot back to standing (Rise from sit,
  Stand up, or ending the pose), waits 3 s, then continues.
- **Disconnect** releases the WebRTC slot so dimOS or the phone app can
  reconnect.

## Object detection and scene counting

The vision components from `muthu` use the same built-in camera and WebRTC
connection as these controls. WASD, direction buttons, full joystick input,
postures, tricks, automatic recovery and STOP keep their existing behavior.
Vision never sends motion commands or opens a second robot connection.

**Live boxes:** leave **Show labeled object boxes** checked on the controls
page to see local YOLO11s detections while driving. Labels include confidence;
predictions below 50% are hidden. One background worker serves both pages.
Uncheck the box for raw video. If the detector fails, the controls automatically
show raw video with an error; toggle boxes off and on to retry. Old camera
frames and observations are discarded on disconnect/reconnect.

For a fresh environment, install the vision dependencies and download the model
from the repository root:

```sh
uv pip install --python ~/dimensional-applications/.venv/bin/python -r robot/requirements-vision.txt
mkdir -p robot/models
curl --fail --location https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11s.pt --output robot/models/yolo11s.pt
```

The model has already been downloaded in this checkout. `GO2_DETECTOR_WEIGHTS`
can point to a checkpoint elsewhere. Model weights and caches are ignored by Git.

**Scene counting:** open **camera object recognition & counting** (`/vision`).
Enter an OpenAI API key under **OpenAI connection**, or supply `OPENAI_API_KEY`
when starting the server. The page keeps the key in server memory until shutdown;
do not put it in source code. `OPENAI_VISION_MODEL` overrides `gpt-4.1-mini`.
Live boxes work locally without an API key. Scene checks send two fresh camera
images to OpenAI and display the inventory and selected-object count.

Set an object description and goal from 1–20, then select **Check this scene**.
Two clear agreeing views are required before grading an answer. **Start
auto-check** runs up to 30 checks, with an 8-second pause between completed
checks. Hiding/leaving the vision page stops sampling. Switching away from
Controls disarms driving; return and press a fresh drive key to enable it again.

The `/api/vision` endpoints use the same `X-Control-Token` as the existing APIs:
`GET /status`, `POST /key`, `/round`, `/scan`, `/start`, `/stop` and `/answer`.
Stopping vision sampling only stops scene analysis; the controls' STOP still
disarms the robot. Live images are processed in memory and are not saved.

## Offline checks

```sh
PYTHONDONTWRITEBYTECODE=1 ~/dimensional-applications/.venv/bin/python -m unittest discover -s robot/tests
node --test robot/tests/*.test.cjs
```

Tests use fake robot/camera/provider transports and do not move hardware or
call OpenAI. They cover the existing controls plus detection, camera session
invalidation, scene counting, authentication and the combined dashboard.
