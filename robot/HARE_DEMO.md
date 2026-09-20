# HARE presenter runbook

Start the `dog` checkout with `robot/start-control-plane.sh`, then open
<http://127.0.0.1:8020/plane>. The page shows **AI STAGES + HB FACES V6**.
The server reads the repository's private `.env.local`, even with plain Uvicorn.
Explicit environment settings override that file. No credentials belong in Git.

The three demo buttons prepare the Mac speaker, connected/default microphone and
Go2 camera automatically. Allow microphone access once. The current Mac defaults
are Whammo speaker output and DJI USB microphone input. No separate Enable or
Save connections clicks are needed. The microphone waits while HARE speaks.

## Demo 1 — Count and Check

HARE says **“Put five objects in front of me.”** Any kind or color of small
movable object counts. Group them clearly in the foreground. People, hands,
furniture, the mat, background clutter and images of objects do not count.

Place four. OpenAI checks two fresh camera frames; when both counts agree with
high confidence, HARE asks **“You have four. How many more do we need?”** Saying
“one” encourages adding it. Place the fifth object: a new camera observation
completes the check and shows **4 + 1 = 5**. A spoken answer alone cannot complete
the physical task. This demo does not command robot movement.

If needed, use **Fallback object count** and **F**. Presenter counts are labelled
as overrides and never claim camera verification.

## Demo 2 — Come Back and Count

HARE first asks for **five objects**. With no object-count progress or answer for
**12 seconds**, it switches to the invitation game. The timeout is configurable
from 5–120 seconds in advanced settings. It works even when camera counting is
unavailable. The monitor distinguishes a timeout assumption from a timeout with
recent camera evidence that no person is visible; neither measures attention or
emotion. **L** is the presenter override for this transition.

The default action output for Demo 2 is **Go2 half-turn + Hello gestures**:

1. HARE makes one half-turn in place, using live IMU heading feedback, then stops.
2. It says **“Come back! Let's play a game together. Count my hellos!”**
3. It performs Hello twice, saying **“Hello!”** after each completed gesture.
4. It asks **“I said hello twice. How many is that?”** Answer **“two.”**
5. It says **“Two! Two hellos means two. Let's add three more.”**
6. It performs three more Hello gestures and asks for the total. Answer **“five.”**
7. It explains **“Five! Two plus three is five. Let's put five objects in front
   of me.”** The camera checks the final group of five.

Keep space clear for standing, turning and waving. The robot never chases anyone
or translates during the turn. The turn stops after approximately 180 degrees
of measured yaw, or fails if heading data goes stale, changes implausibly, or the
20-second limit is reached. There is no blind timed-turn fallback. The robot's
existing recovery/Hello command path is reused; a refused action stops the demo.
These protections are tested in simulation; physical heading direction and the
actual gesture must still be checked on this Go2.

Choose **Screen Hello gestures** for voice with visual gestures and no movement.
**Caption rehearsal** also skips microphones, providers and robot connection.

## Demo 3 — Soft Hands

Show a clear Go2 view first. Cover the Go2 camera until its image is black for
about one second. The detector requires three or more advancing frames spanning
at least half a second after a clear baseline. This is the staged rough-touch
cue; do not actually hit the robot. A disconnected/stale camera, a brief flicker,
or an image that was already black at startup cannot trigger it.

HARE then says:

- **“Ouch, that was too hard. Softer, please.”**
- **“Other people and animals feel pain too.”**
- **“Show me soft hands now.”**

After the gentle touch, press **G**. HARE says **“Perfect. Soft hands.”** Gentle
touch remains a presenter event; there is no touch or force sensor. **B** remains
the bump fallback. The black-camera cue is deliberately labelled as a demo cue,
not proof of an impact or pain. Uncover the camera after the cue.

## OpenAI stages and HB expressions

OpenAI receives two in-memory Go2 frames and the current lesson context, including
the latest answer. It returns an allowed stage, two object counts, confidence,
visible-person evidence, an expression, and a short reason. The dashboard shows
this estimate and its source. Counts require agreement and high confidence.
Black-image checks are validated locally; model text cannot fake a bump.
Late replies from before STOP, a phase/question change, or a presenter override
are discarded. The model cannot invent arbitrary motion or jump lesson steps.

The implementation uses the Responses API's
[structured output format](https://developers.openai.com/api/docs/guides/structured-outputs),
with `store: false`, bounded requests, and server-side validation. Real camera
frames go to OpenAI while a live demo runs; raw microphone audio goes to Deepgram,
and HARE's speech goes to ElevenLabs. Keys never go to device pages or models.

The eight HB names are **Ready, Watching, Encourage, Thinking, Go, Celebrate,
Rest, Soft confused**. AI choices go to the local preview, paired display pages,
and HB's existing `/emote` endpoint. No board redeploy is needed. See
[HB_FACE.md](HB_FACE.md) for the README's wireless setup and port checks.
Keys **1–8** or the face switcher hold a manual expression until **Resume AI
expressions** or the next demo. A configured server and a connected physical
screen are separate monitor states.

## Presenter controls

| Key | Action |
| --- | --- |
| F | Apply the visible fallback object count |
| L | Trigger Demo 2's invitation sequence |
| B | Trigger the staged bump fallback |
| G | Confirm the gentle-touch presenter cue |
| 1–8 | Hold an HB expression manually |
| Space | STOP and disarm |

Shortcuts do not fire while typing. Keep the dashboard focused. STOP, lost focus,
controller loss, robot loss during physical actions, or speaker failure cancels
the sequence. Camera loss/covering blocks physical actions. A firmware gesture
already accepted by the robot may still finish. No action is retried automatically.

Closing/backup slides, component tests, the old blocks activity and tool reference
remain in advanced controls. `/controls` retains direct driving controls;
`/vision` retains the independent vision page. This Python server uses Unitree
WebRTC directly and does not run a dimOS process.
