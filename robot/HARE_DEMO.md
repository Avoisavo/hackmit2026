# HARE presenter runbook

Start the `dog` checkout with `robot/start-control-plane.sh`, then open
<http://127.0.0.1:8020/plane>. The build label includes **DEMO VIEWS V8**.
The server reads the repository's private `.env.local`, even with plain Uvicorn.
Explicit environment settings override that file. No credentials belong in Git.

The three demo buttons prepare the Mac speaker, connected/default microphone and
Go2 camera automatically. Allow microphone access once. The current Mac defaults
are Whammo speaker output and DJI USB microphone input. No separate Enable or
Save connections clicks are needed. The microphone waits while HARE speaks.
**Go2 gestures** is the default for all three demos. **Setup & advanced controls
→ Demo options** offers screen rehearsal and the optional forward jump. The
movement monitor names each action; the event log records completed commands.
The selected demo shows only its controls: Demo 1 has count and maths-answer
fallbacks; Demo 2 adds the walk-away cue, inactivity timer and jump option; Demo 3
shows bump, apology and gentle-touch controls. STOP and system status stay visible.
Face overrides, hardware tests and manual movements are under advanced controls.

## Demo 1 — Count and Check

HARE says **“Let's play a counting game! Can you put five objects in front of me?”** Any kind or color of small
movable object counts. Group them clearly in the foreground. People, hands,
furniture, the mat, background clutter and images of objects do not count.

Place four. OpenAI checks two fresh camera frames; when both counts agree with
high confidence, HARE asks **“I spy four! We're aiming for five. How many more do we need?”** Saying
“one” encourages adding it. Place the fifth object: a new camera observation
completes the check and shows **4 + 1 = 5**. A spoken answer alone cannot complete
the physical task. HARE stays still while objects are placed and questions are
answered. Completing the five-object mission triggers one **Content** celebration
after the success line. There are no opening or mid-answer tricks.

If needed, use **Fallback object count** and **F**. Presenter counts are labelled
as overrides and never claim camera verification.

## Demo 2 — Come Back and Count

HARE first asks for **five objects**. With no object-count progress or answer for
**12 seconds**, it switches to the invitation game. The timeout is configurable
from 5–120 seconds in advanced settings. It works even when camera counting is
unavailable. The monitor distinguishes a timeout assumption from a timeout with
recent camera evidence that no person is visible; neither measures attention or
emotion. **L** is the presenter override for this transition.

Demo 2 stays still during its object mission. After the inactivity/leave cue:

1. HARE makes one half-turn in place, using live IMU heading feedback, then stops.
2. It says **“Game switch! Come back! Let's count my silly hellos together!”**
3. It performs Hello twice, saying **“Hello!”** after each completed gesture.
4. It asks **“Your turn, counting buddy! How many hellos did you count?”** Answer **“two.”**
5. It says **“Two! You got it! Two hellos means two. Ready for three more?”**
6. It performs three more Hello gestures and asks for the total. Answer **“five.”**
7. It explains **“Five! Woohoo! Two plus three is five. Let's try our five-object
   mission again!”** The camera checks the final group of five. Completing that
   mission triggers one **Content** celebration. No other gestures interrupt the
   Hello counting sequence.

For a jump, select **Demo 2: add one forward celebration jump** before starting.
This confirms at least 2 m of clear, flat space ahead with people and objects
outside the landing area. After the answer **five**, HARE asks for room and
performs one tested **FrontJump**, then returns to objects.
The jump moves forward; it is not an in-place hop. The checkbox is off by default,
applies only to Demo 2, and never enables jumps in screen/caption rehearsal or
the camera AI's unrestricted tool loop. A refusal stops the demo without retry.

Keep space clear for standing, turning and waving. The robot never chases anyone
or translates during the turn. The turn stops after approximately 180 degrees
of measured yaw, or fails if heading data goes stale, changes implausibly, or the
20-second limit is reached. There is no blind timed-turn fallback. The robot's
existing recovery/Hello command path is reused; a refused action stops the demo.
These protections are tested in simulation; physical heading direction and the
actual gesture must still be checked on this Go2.

Choose **Screen rehearsal** for voice with visual gestures and no movement.
**Caption rehearsal** also skips microphones, providers and robot connection.

## Demo 3 — Soft Hands

HARE is ready for the bump cue immediately and stays still. Show a clear Go2 view,
then cover the Go2 camera until its image is black for
about one second. The detector requires three or more advancing frames spanning
at least half a second after a clear baseline. This is the staged rough-touch
cue; do not actually hit the robot. A disconnected/stale camera, a brief flicker,
or an image that was already black at startup cannot trigger it.

HARE then says:

- **“Ouch! A little softer, please. Let's practise gentle hands together.”**
- **“People and animals need gentle care too.”**
- **“Can you say, sorry HARE? Then we can try again together.”**

The microphone opens after the question. Say **“Sorry, HARE”** or **“I'm sorry.”**
HARE waits for an apology, then says:

- **“Thank you for saying sorry! That was kind. We're a team!”**
- **“Ready for gentle paws? Show me your soft hands.”**

If the mic misses the apology, press **I apologized** in **Demo 3 controls**.
It submits **“Sorry, HARE”** automatically; no typing is needed. The button becomes
available after HARE asks for an apology. Caption rehearsal uses this same button.

After the gentle touch, press **G**. HARE says **“Lovely soft hands! Thank you for being gentle with me.”** Gentle
touch remains a presenter event; there is no touch or force sensor. **B** remains
the bump fallback. The black-camera cue is deliberately labelled as a demo cue,
not proof of an impact or pain. Uncover the camera after the cue.
In Go2 mode, it adds **“Step back and I'll send you a heart!”**, then performs
**Heart** after the line finishes. There is no motor action during the rough-touch,
apology or gentle-touch waiting phases. Demo 3 never jumps.
G also works during the **“Show me your soft hands”** sentence: it records one
cue and waits for that sentence to finish. It cannot skip the apology. STOP clears
pending cues. Early/repeated cues show the current next step without replaying
speech or triggering a motion.

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
Only shortcuts belonging to the selected demo send requests. Controls are enabled
for the current step, and the **Next step** line tells the presenter what to do.

Closing/backup slides, component tests, the old blocks activity and tool reference
remain in advanced controls. `/controls` retains direct driving controls;
`/vision` retains the independent vision page. This Python server uses Unitree
WebRTC directly and does not run a dimOS process.
