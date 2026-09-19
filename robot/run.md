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
cd ~/Developer/mit
export ROBOT_IP='172.20.10.4'
python -m uvicorn app:app --host 127.0.0.1 --port 8010
```

Then open http://127.0.0.1:8010 in a browser on this Mac.

The server does not reload `app.py` on its own: after any change to it,
Ctrl+C and start it again. After **every** server restart, reload the
browser tab, because the page holds a per-run session token (the page tells
you when this is needed).

Any free port works. Port 8000 on this machine is held by
`solana-test-validator`, which is why the old command failed to bind.
`fastapi` and `uvicorn` are already installed in that venv; if not,
`uv pip install fastapi uvicorn` with the venv active.

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
2. **Stand up**.
3. **Balance stand**. The robot only follows joystick input in balance stand.
4. **Enable movement**, then hold W/S (forward/back), Q/E (strafe),
   A/D (turn) or the on-screen buttons. Releasing sends zero input.
5. **Space** or the red STOP button disarms. Any posture button also disarms.

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
- **Tricks**: Hello, Stretch, Heart, Content, Scrape, Wiggle hips, Sit,
  Rise from sit, Dance 1/2, Recovery stand, and the orange ones: Stand on
  hind legs, Handstand, Jump forward, Pounce, Front/Back/Left/Right flip,
  Damp (go limp). Orange tricks ask for confirmation. Give the robot at
  least 2 m of clear, flat space. A trick that does not exist in the current
  mode (for example Wiggle hips or Right flip in `ai` mode) returns 409.
- Every trick and posture disarms driving; click Enable movement afterwards.
- **Disconnect** releases the WebRTC slot so dimOS or the phone app can
  reconnect.
