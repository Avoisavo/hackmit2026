# Go2 web dashboard

For HARE, use `~/Developer/hackmit2026/robot/start-control-plane.sh` and
<http://127.0.0.1:8020/plane>. It loads the private environment file.
[HARE_DEMO.md](HARE_DEMO.md) covers the demo flow. The manual instructions below
remain available at `/controls` on whichever port you start.

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
object boxes** checkbox under the camera, an **AI camera control** panel, and an
**Open camera object recognition & counting** link. If any are missing, stop the old server and use the explicit
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

## Connection recovery

**Connected · Disarmed** means the robot link is still up but driving has
stopped. The hint names the stop reason. Losing focus or missing dashboard
heartbeats still stops movement immediately.

If the dashboard socket drops, this tab reconnects automatically with delays
from 1 to 10 seconds. It waits for the server to confirm that it owns controls.
A second tab that is refused ownership cannot arm or stop the owning tab through
its background events; the explicit STOP button remains global. Close the other
controls tab and click **Reconnect controls** to take ownership.

If an established robot WebRTC link drops, the server disarms, cancels pending
automatic recovery, and gives the existing peer 3 seconds to recover. It then
tries a fresh connection up to three times, with 2 and 5 seconds between failed
attempts. Reconnection restores camera and telemetry while movement remains
disarmed. Release any held movement keys, then press again to drive.
**Disconnect** cancels pending robot reconnect attempts and closes a partially
connected peer. Exhausted retries require **Connect robot** again.

The terminal logs failed sends and robot transport state at a drop. Authenticated
`GET /api/status` includes `transport` (peer, ICE and data-channel states),
`dashboard_connected`, `reconnecting`, `connection_message` and `last_stop_reason`.
A failed keepalive or zero-input send no longer terminates the heartbeat/watchdog.
After restarting the server, reload the page to obtain its new session token.

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

## AI camera control

On the controls page, **AI camera control** uses the live robot camera and your
goal to choose actions through OpenAI function calling. It shares the existing
robot connection and manual controller; no second WebRTC client is opened.

1. Restart the Python server with the explicit `--app-dir` command above and
   reload the controls tab. Connect the robot and wait for the camera.
2. Enter your OpenAI API key in the AI panel and click **Save key for this session**.
   The key stays in server memory, is shared with scene counting, and is cleared
   from the password field after submission. `OPENAI_API_KEY` also works.
3. Enter a goal, for example **Wave once when a person is in front of you, then stop.**
   Click **Start AI** while the robot is disarmed and this tab owns controls.
4. Keep the tab focused. The panel displays each tool, its arguments and reason,
   and the result. **Stop AI**, the main **STOP** button, or Space cancels the run.

Starting AI sends your goal and fresh camera JPEGs to OpenAI. This mode can move
the real robot; a monocular image cannot measure clearance or provide reliable
obstacle avoidance. Local object boxes alone do not need OpenAI. The firmware's
**Switch to AI** motion mode is separate from this camera agent.

The loop is **fresh frame → one model tool call → validated action → new frame**.
Tool results say whether commands were accepted; they do not prove that the
physical action succeeded. The next image lets the model assess the outcome.
The server provides:

- `move_robot`: forward, turn left, or turn right, 0.1–1 second at 0.1–0.3 joystick
  input, then zero input. This is not a distance or calibrated speed command.
- `set_posture`: stand, balance, or lie down.
- `perform_trick`: hello, stretch, heart, content, scrape, wiggle hips, sit,
  rise from sit, dance 1 or 2. Existing motion-mode restrictions still apply.
- `wait`: stay stopped for 0.2–2 seconds, then check a new frame.
- `finish`: stop the run and explain completion or why it cannot continue.

Runs stop after at most **6 decisions**, with a **120-second execution limit**.
The server rejects malformed arguments, unlisted tools, flips/jumps/held poses,
multiple calls in one response, stale decisions, and refused robot commands.
Camera frames must be under 2 seconds old; decisions must be under 8 seconds old
when the requested motion starts, including time spent preparing the stance.
Slow model responses may therefore stop a run without performing its action.

STOP, tab/focus loss, dashboard heartbeat loss, a stale camera, connection changes,
or manual input cancels AI. A delayed provider reply cannot restart motion.
Reconnect never resumes AI. A pending provider request may keep **Start AI**
disabled until its response/timeout is discarded; manual controls remain usable.
The first drive key during AI cancels it; release and press again for manual drive.
Space can be typed in the goal field while stopped; it becomes STOP there during AI.

AI actions use the existing stance recovery before motion, but AI gestures do
**not** schedule the manual trick controller's automatic rearm. They wait for
their configured duration before another camera decision. AI ends disarmed;
the next manual drive press recovers as needed. STOP cancels subsequent commands
and sends zero joystick input; a firmware trick already accepted may still finish.

The implementation uses the [OpenAI Responses function-calling API](https://developers.openai.com/api/docs/guides/function-calling/)
with strict schemas, one tool per decision, and `store: false`. The default model
is `gpt-4.1-mini`; `OPENAI_CONTROL_MODEL` can select another model supporting images
and Responses function calling. The key is never sent to the robot or echoed in
API responses. Camera images are processed in memory and not saved by this app.

Authenticated endpoints: `GET /api/ai/status`, `POST /api/ai/key`, and
`POST /api/ai/start`. Starting requires this tab's WebSocket `control_id`, the
current `stop_epoch` as `control_epoch`, a unique `run_id`, and `goal`. It cannot
start from a rejected second tab or replay a start request from before STOP.
Use the existing `POST /api/stop` to cancel. Add future tools to `ai_agent.py`
and implement their validated actuator behavior in `app.py:execute_ai`.

## Offline checks

```sh
PYTHONDONTWRITEBYTECODE=1 ~/dimensional-applications/.venv/bin/python -m unittest discover -s robot/tests
node --test robot/tests/*.test.cjs
```

Tests use fake robot/camera/provider transports and do not move hardware or
call OpenAI. They cover the existing controls plus detection, camera session
invalidation, scene counting, AI tool validation, bounded motion, cancellation
races, authentication and the combined dashboard. Live OpenAI decisions and
physical behavior still require verification with your robot and API key.
