# HARE: one server and one control plane

The three current demos are documented in [HARE_DEMO.md](HARE_DEMO.md).
The original blocks activity remains available in the collapsed activity section.

This isolated integration combines the Go2 backend, built-in camera counting,
Deepgram microphone input, ElevenLabs speech output, and HB's face expression API.
Audio uses the Bluetooth speaker and microphone selected on the Mac. Test the
Whammo 2.0 speaker output first, then the connected microphone input. One
FastAPI/Uvicorn process coordinates the demos. HB keeps its existing board face
server; no second laptop panel or Next.js server is required. Parent video and
Insta360 are intentionally outside this version.

The control plane now lives on the `dog` branch in
`/Users/derek/Developer/hackmit2026`. The former integration checkout is not needed
to run it.

## Start locally

```sh
~/Developer/hackmit2026/robot/start-control-plane.sh
```

Open **http://127.0.0.1:8020/plane** on this Mac. The original robot controls are
still at `/controls`; `/` redirects to `/plane`. The independent scene-counting page remains at `/vision`.
Only one operator page can own the robot control WebSocket.

The server automatically loads `/Users/derek/Developer/hackmit2026/.env.local`,
even with plain Uvicorn and a different working directory. Explicit environment
variables take precedence.
This file is ignored by Git and readable only by your macOS account. The active
Python server reads `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`, and
`ELEVENLABS_VOICE_ID`. It also reads `OPENAI_API_KEY` when provided; that key is
needed for camera analysis, not audio tests. Restart after changing the file. The dashboard has no credential entry form.

`ELEVENLABS_AGENT_ID` and `NEXT_PUBLIC_ELEVENLABS_CONNECTION` belong to the
separate conversational-agent demo. This coordinator uses ElevenLabs TTS.
`BOARD_URL` or the existing `NEXT_PUBLIC_ROBOT_FACE_URL` configures the HB face
bridge; the local IPv4/IPv6 reverse tunnel is detected automatically. See
[HB_FACE.md](HB_FACE.md) for the setup from HB's README.

This server does not connect to or move the robot at startup. Before connecting,
disconnect the old Go2 server / dimOS / phone app, because the robot accepts one
WebRTC client. The existing server on port 8010 was not stopped or modified.

The existing Python venv already supplies the required packages. In a new venv,
install `robot/requirements.txt`. No npm install or Next build is required.
The control-plane camera uses the existing raw camera and OpenAI two-view count;
local YOLO weights are only needed for the advanced controls' optional boxes.

## Connect the demo

1. Provider settings come from `.env.local`. The monitor shows configured/missing
   states without exposing keys. OpenAI is needed for camera analysis, Deepgram
   for transcription, ElevenLabs and its voice ID for speech.
2. Choose **Whammo 2.0 Speaker** as the Mac output and your connected microphone
   (such as DJI Wireless Microphone RX) as the default input.
   Click one of the three demo buttons. It prepares the speaker and microphone
   together, requests browser permission once, and waits for the transcription
   connection before starting. The Go2 Air uses this external audio path.
   Optional tests prepare their own audio; no Enable button is required first.
3. The monitor shows the connected microphone, input level and playback state.
   The mic waits while HARE speaks. Only final Deepgram transcripts grade answers.
   Use **Manual override** for typed answers and presenter cues. Advanced controls
   include **Reconnect speaker** and **Reconnect microphone** after changing devices.
4. The existing HB board receives expressions automatically over its tunnel or
   configured LAN address. Its monitor must report a connected screen, not merely
   loaded settings. Keys 1–8 provide a manual override; Resume AI expressions
   returns control to the model. Optional paired browser displays still work.
5. All three demo buttons connect the Go2 camera. Demos 1 and 2 count five objects
   of any color. OpenAI identifies the current stage, count and appropriate face.
   The legacy Analyze blocks test remains separate under advanced controls.
6. All demos default to physical Heart/Content gestures. Demo 2 also turns and
   counts Hello gestures after 12 seconds without progress. Its turn requires live
   heading feedback; an optional forward celebration jump requires the clear-space
   checkbox. Demo 3 uses clear-to-black camera frames as its staged bump cue,
   asks for an apology, and stays still during touch. B/G presenter fallbacks and
   screen rehearsal remain available. See the current [runbook](HARE_DEMO.md).

Each role supports one active device tab. Pairing it again revokes its previous
link. Devices must be paired again after a server restart. A disconnected device
does not resume an interrupted activity automatically. Pairing links are access
credentials for their narrow role; share them only with the intended device.

## Phone and Arduino over the network

The phone microphone requires a **trusted HTTPS origin**. Plain `http://<Mac-IP>`
does not provide a usable browser microphone. Localhost is suitable for a local
microphone test on the Mac, including the selected microphone. Sound plays through
the selected Mac output (Whammo), or an optionally paired browser speaker player.

Use a certificate trusted by the phone and board, covering the LAN hostname/IP
and `localhost`. Provide its certificate and private-key files to this same
Uvicorn server. For example, replace the address and file paths here:

```sh
export CONTROL_HOSTS='192.168.1.40'
~/dimensional-applications/.venv/bin/python -m uvicorn app:app \
  --app-dir /Users/derek/Developer/hackmit2026/robot \
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
audibility; confirm the tone plays through Whammo before
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
cd /Users/derek/Developer/hackmit2026
PYTHONDONTWRITEBYTECODE=1 ~/dimensional-applications/.venv/bin/python -m unittest discover -s robot/tests
node --test robot/tests/*.test.cjs
```

Tests use fake providers, audio buffers and robot/camera transports. They exercise
the exact wrong-then-correct sequence, retained camera updates, scoped credentials,
stale data, concurrent ownership, failed speech, canceled audio, and late replies.
The physical Go2, selected microphone, Whammo speaker, display, and real provider
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
header **DEMOS · V4** identifies the HARE update.

The **Movement tool map** is generated from the exact `ai_agent.TOOLS` schemas
used in OpenAI requests. **Download tool schemas** exports the schemas, dispatch
example, limits, all manual movements, and component endpoints. See
[AI_TOOLS.md](AI_TOOLS.md) for the API table and caller example.

Implementation references:
- [Driver audio streaming example](https://github.com/legion1581/unitree_webrtc_connect/blob/master/examples/go2/audio/internet_radio/stream_radio.py)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)

These are offline-verified integration paths. Audible Whammo playback, microphone capture,
and provider credentials require testing with the connected devices.
