# Buddy: one server and one control plane

This isolated integration combines the Go2 backend, built-in camera counting,
Deepgram microphone input, ElevenLabs speech output, and HB's Twinkle face.
Audio uses the Bluetooth speaker and microphone selected on the Mac. Test the
Whammo 2.0 speaker output first, then its microphone input. One FastAPI/Uvicorn process serves everything. The Mac and Arduino are browser
clients. They do not need another Next.js or face backend. Parent video and
Insta360 are intentionally outside this version.

The original checkout at `/Users/derek/Developer/hackmit2026` is unchanged. This
copy is on `integration/control-plane` in `/Users/derek/Developer/hackmit2026-control-plane`.
This is a separate permanent checkout with no shared Git object storage.

## Start locally

```sh
~/Developer/hackmit2026-control-plane/robot/start-control-plane.sh
```

Open **http://127.0.0.1:8020/plane** on this Mac. The original robot controls are
still at `/controls`; `/` redirects to `/plane`. The independent scene-counting page remains at `/vision`.
Only one operator page can own the robot control WebSocket.

The launcher loads `/Users/derek/Developer/hackmit2026-control-plane/.env.local`.
This file is ignored by Git and readable only by your macOS account. The active
Python server reads `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`, and
`ELEVENLABS_VOICE_ID`. It also reads `OPENAI_API_KEY` when provided; that key is
needed for camera analysis, not audio tests. UI-saved keys last until restart.

`ELEVENLABS_AGENT_ID`, `NEXT_PUBLIC_ELEVENLABS_CONNECTION`, and
`NEXT_PUBLIC_ROBOT_FACE_URL` are retained for the Next.js demo. The Python blocks
coordinator uses ElevenLabs TTS, not a separate conversational agent, and drives
its face via the paired face page rather than the legacy board URL.

This server does not connect to or move the robot at startup. Before connecting,
disconnect the old Go2 server / dimOS / phone app, because the robot accepts one
WebRTC client. The existing server on port 8010 was not stopped or modified.

The existing Python venv already supplies the required packages. In a new venv,
install `robot/requirements.txt`. No npm install or Next build is required.
The control-plane camera uses the existing raw camera and OpenAI two-view count;
local YOLO weights are only needed for the advanced controls' optional boxes.

## Connect the demo

1. Enter provider credentials under **Provider connections**: OpenAI key,
   Deepgram key, ElevenLabs key, and an ElevenLabs voice ID accessible to your
   account. Inputs are cleared on submit. Keys stay in server memory and are
   never included in device pairing links or status responses. Environment
   variables `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`, and
   `ELEVENLABS_VOICE_ID` also work.
2. Pair **Whammo 2.0 Speaker** over Bluetooth. In **System Settings → Sound**,
   select it under **Output**. Test output before enabling the microphone. Click **Use this
   computer’s speaker**, then **Play speaker test tone** under **Quick tests**.
   The 0.8-second tone needs no API key or Go2 connection. Click **Test ElevenLabs
   voice** after saving the voice key and ID. Go2 Air uses this external audio
   path; this installation does not send speech to the robot's audio transceiver.
3. With the Deepgram key loaded, click **Use this microphone**; choose
   **Whammo 2.0 Speaker (Bluetooth)** in the browser's microphone prompt and allow
   access. If you change inputs, click the button again to reopen capture. You can optionally pair a phone using the HTTPS setup below.
   The microphone client sends final Deepgram transcripts;
   partial transcripts never grade answers. **Listen for 20 seconds** shows test
   transcripts and the local microphone level without starting an activity. The microphone waits while the robot
   speaks. **Operator answer fallback** can exercise answers before the mic joins.
4. **Pair Arduino / face display**. Open the pairing URL in the Arduino's
   Chromium kiosk, with the ASUS display connected to the board. The device page
   uses the same Twinkle renderer as `hb` and receives the coordinator's expression.
   The board's old Python `server.py` is not needed for this page. The operator
   always has a local expression preview as well.
5. Enter the Go2 IP and connect. Wait for **camera live** and click **Analyze blocks now** to check vision. Keep a clear view of
   the toy blocks; the count is specifically for toy blocks, not total detections.
6. Choose the target (default three). Optionally enable **one Hello gesture**;
   it is off by default and needs room for the robot's existing stand/recovery
   sequence. Click **Start blocks activity** and keep the operator tab focused.

Each role supports one active device tab. Pairing it again revokes its previous
link. Devices must be paired again after a server restart. A disconnected device
does not resume an interrupted activity automatically. Pairing links are access
credentials for their narrow role; share them only with the intended device.

## Phone and Arduino over the network

The phone microphone requires a **trusted HTTPS origin**. Plain `http://<Mac-IP>`
does not provide a usable browser microphone. Localhost is suitable for a local
microphone test on the Mac, including the DJI microphone. Sound plays through
the selected Mac output (VISA), or an optionally paired browser speaker player.

Use a certificate trusted by the phone and board, covering the LAN hostname/IP
and `localhost`. Provide its certificate and private-key files to this same
Uvicorn server. For example, replace the address and file paths here:

```sh
export CONTROL_HOSTS='192.168.1.40'
~/dimensional-applications/.venv/bin/python -m uvicorn app:app \
  --app-dir /Users/derek/Developer/hackmit2026-control-plane/robot \
  --host 0.0.0.0 --port 8020 --no-proxy-headers \
  --ssl-certfile /absolute/path/buddy-cert.pem \
  --ssl-keyfile /absolute/path/buddy-key.pem
```

Open **https://localhost:8020/plane** on the Mac. Set **Server address for other
devices** to `https://192.168.1.40:8020`, then generate the pairing links. The
phone, board and Mac must be able to reach each other on that network. A captive
Wi-Fi network with client isolation will not work for these LAN connections.

`CONTROL_HOSTS` is a comma-separated list of additional exact hostnames/IPs.
Localhost and 127.0.0.1 are already allowed. The operator pages are restricted to
loopback clients; LAN device pages never receive the operator's token. Keep
`--no-proxy-headers` for this direct deployment so forwarded headers cannot make
a network client look like a local operator. Do not expose the operator through
a local reverse proxy without adding its own authentication and reviewing this
boundary. No certificates, keys or network settings were installed by this work.

## Shared activity behavior

The coordinator owns a session ID, current question ID, observed count, speech
ID, and one expression. It computes arithmetic locally; OpenAI supplies the
camera observations, Deepgram supplies complete utterances, and ElevenLabs reads
the coordinator's current line.

| Event | Response |
| --- | --- |
| Start | Ask for three blocks; Watching face |
| Clear agreeing camera views show two | Ask how many more; Thinking face |
| Child answers two | Encourage; repeat the **how many more** question |
| Child answers one | Praise; Celebrate; optional one Hello gesture |
| Speech and optional gesture finish | Complete, with robot movement disarmed |
| Camera already observes the full target | Celebrate and mark physical task complete |
| Ambiguous answer | Ask for one clear answer; do not guess |
| Count expires or changes | Recheck the scene before grading |
| Empty view | Wait for blocks without prematurely asking a math question |

A correct spoken answer sets `answer_correct`; it does **not** set `task_complete`
unless the camera actually observed all the blocks. This version finishes the
specified demo after the correct answer and celebration. The microphone can also
stop an activity with a clear “stop”, “please stop”, “goodbye”, or “take a break”.

Camera observations received during speech are retained and revalidated when
playback ends. Browser playback advances after its audio source reports that it
ended, not when the TTS HTTP request returns. This does not verify physical
audibility; confirm the tone plays through VISA before
starting the activity. Duplicate speech/transcript events cannot repeat a gesture or
advance a different question. Provider errors stop the activity instead of
pretending a line was spoken. Devices poll serialized state every 300 ms; no
commands are replayed when they reconnect.

STOP ALL, operator focus loss, the existing dashboard heartbeat timeout, robot
disconnect, stale camera, or loss of an active audio device cancels the activity.
The standalone camera-driving agent and lesson coordinator cannot own the robot
simultaneously. Other scene-counting pages cannot change the lesson's target or
key while it is active. A gesture already accepted by firmware may finish even
after software STOP; subsequent commands and automatic rearming are canceled.

The activity has a ten-minute limit, a 60-second speech deadline, and bounded
provider request timeouts. Existing camera freshness/consensus rules still apply.

## Code and provenance

- `go2_speaker.py`: retained optional WebRTC audio implementation and tests;
  not attached or used for this Go2 Air installation.
- `control_plane.py`: shared session, condition handling, scoped device APIs,
  provider adapters, cancellation, and one-shot gesture dispatch.
- `plane_web/operator.html`, `operator.js`, `plane.css`: the central dashboard.
- `plane_web/device.js`, `device.html`: microphone, speaker and face clients.
- `plane_web/deepgram.js`: adapted from `deepgram` **b6e1281**, using role-scoped
  credentials and cancellation guards. No separate ElevenLabs conversational
  agent runs alongside the activity.
- `plane_web/twinkle.js`: HB's renderer from `hb`/`main` **79e4191**, unchanged.
- Existing robot, camera and vision code: `dog` **8a8ac50**.
- `app.py`: mounts everything into the same server and preserves robot STOP,
  connection recovery, camera sharing and controller ownership.

No parent video, Insta360 capture, network discovery, certificate installation,
or firmware changes are included. No live provider calls or hardware movements
were performed during implementation.

## Offline validation

```sh
cd /Users/derek/Developer/hackmit2026-control-plane
PYTHONDONTWRITEBYTECODE=1 ~/dimensional-applications/.venv/bin/python -m unittest discover -s robot/tests
node --test robot/tests/*.test.cjs
```

Tests use fake providers, audio buffers and robot/camera transports. They exercise
the exact wrong-then-correct sequence, retained camera updates, scoped credentials,
stale data, concurrent ownership, failed speech, canceled audio, and late replies.
The physical Go2, DJI microphone, VISA speaker, display, and real provider
credentials still need a supervised end-to-end run.

## Tests and AI movement map

The landing page has explicit tests for an external speaker tone, ElevenLabs voice, microphone
transcription, camera counting, face expressions, and robot posture / short steps.
Every physical movement is an explicit button press; opening the page, reading the
catalogue, and configuring keys do not command the robot. The guarded movement
tests require a fresh camera, focused operator tab, and valid current control ID
and STOP epoch. Each ends disarmed. STOP / focus loss invalidates pending tests,
clears browser playback, and rejects late speech generation. The audio tests
require a focused operator tab but work with the robot disconnected. The page
header **GO2 AIR + AUDIO · V3** identifies this audio update.

The **Movement tool map** is generated from the exact `ai_agent.TOOLS` schemas
used in OpenAI requests. **Download tool schemas** exports the schemas, dispatch
example, limits, all manual movements, and component endpoints. See
[AI_TOOLS.md](AI_TOOLS.md) for the API table and caller example.

Implementation references:
- [Driver audio streaming example](https://github.com/legion1581/unitree_webrtc_connect/blob/master/examples/go2/audio/internet_radio/stream_radio.py)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)

These are offline-verified integration paths. Audible VISA playback, DJI capture,
and provider credentials require testing with the connected devices.
