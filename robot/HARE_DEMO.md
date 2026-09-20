# HARE presenter runbook

Run the `dog` branch from `~/Developer/hackmit2026`:

```sh
~/Developer/hackmit2026/robot/start-control-plane.sh
```

Open <http://127.0.0.1:8020/plane>. The dashboard includes **Demo 1**, **Demo 2**, **Demo 3**, a live system monitor,
and manual overrides.
The server reads the repository's ignored `.env.local`, including when started
with a plain Uvicorn command from another directory. Explicit environment variables
override the file. Credentials are not in Git. Only one server can use port 8020. If it is already running, use that page
or stop that server before starting another. `/controls` retains the working
manual controls and `/vision` retains the independent counting page.

## Before presenting

1. Choose **Whammo 2.0 Speaker** as the Mac's sound output; the connected DJI USB
   microphone or your chosen default input supplies speech.
   Click **Demo 1**, **Demo 2**, or **Demo 3**. That click enables browser audio,
   pairs this computer's speaker and microphone, and waits for Deepgram to connect
   before starting the lesson. Allow microphone access if the browser asks. Devices
   are reused across demos. No separate Enable or Save connections click is needed.
2. Watch **System monitor** for the speaker, selected microphone, input level,
   provider configuration, robot, camera, movement and face display. The mic waits
   while HARE speaks. Ready confirms the browser connection, not physical audibility.
   Optional sound/mic tests and reconnect buttons are under **Setup & advanced controls**.
   **Manual override** exposes count and touch cues, plus typed answers.
3. Demos 1 and 2 connect the Go2 camera automatically. `OPENAI_API_KEY` in
   `.env.local` is required for camera analysis; restart after adding it. Without
   that key or camera, use the clearly labelled count override. Deepgram and
   ElevenLabs alone do not analyze camera frames. Counts include color and the mat.
4. Use **Pair Arduino / face display** for the display page. It shows the face,
   equation/count, ear wobble, and hop animation. LAN setup is described in
   [CONTROL_PLANE.md](CONTROL_PLANE.md).
5. Choose **Screen hops** when there is no room. **Go2 forward jumps** uses the
   tested `front_jump` action; it is not an in-place hop. That mode requires a
   fresh Go2 camera and the clear-path checkbox. Point HARE away from the learner
   and allow for all six forward jumps in Run, Play. No tracking or chasing runs.

Opening a page or selecting a mode never moves the robot. Starting a demo in
Go2 mode authorizes its fixed, bounded sequence. Each jump uses the existing
posture/recovery logic, waits for its configured completion, and leaves driving
disarmed. A refused command stops the sequence; there is no retry or auto-rearm.
Timing depends on speech latency, robot recovery, and the teammate's responses;
rehearse the 45/60/25-second targets with the actual hardware.

## 1 — Count and Check

Say: **“HARE checks a real answer, not a tap on a screen.”**

Select **Demo 1**. HARE asks for three blue blocks on the mat.
Place two. Two fresh, agreeing camera views produce the count **2** and HARE
asks, **“You have two. How many more do we need?”** Add one block. Only a fresh
count of three completes the physical check, displays **2 + 1 = 3**, and cues
one hop/jump. Saying “one” encourages placing it but never completes the task.

If vision analysis fails, set **Fallback block count** to `2`, press **F**,
then change it to `3` and press **F** after adding the third block. The display
labels these readings **Presenter fallback** and `task_complete` remains false;
they are not represented as camera verification.

## 2 — Run, Play, Teach Again

Say: **“Watch what happens when the learner stalls.”**

Select **Demo 2**. HARE asks for five red blocks. Ten seconds
without count progress, backed by a recent block observation, changes the lesson.
For reliable stage timing, press **L** when your teammate walks away. The log
identifies this as a presenter cue; no emotion or diagnosis is inferred.

HARE says **“You need to move. Let's move together!”**, performs one departure
hop/jump, then says **“Catch me!”**. It stops travelling between actions and says
**“I hopped. Count my hops!”**, then performs three hops/jumps. Say **“Three.”**
HARE says **“Three! Now add two more.”**, performs two more, and waits for **“Five.”**
HARE says **“Five. Same as five red blocks. Let's go back.”** The teammate returns
and places five red blocks. The camera checks the completed mission. **F** is
available here too. The robot does not navigate back or chase the teammate.

Say: **“The learner never escaped the maths. The maths changed shape. Blocks became hops.”**

## 3 — Soft Hands

Say: **“HARE is a creature. The learner practises care on HARE.”**

Select **Demo 3**. Use your own teammate, never a judge. **B** cues the
hard bump and makes the on-screen ears wobble. HARE says, in order:

- “Ouch, that was too hard. Softer, please.”
- “Other people and animals feel pain too.”
- “Show me soft hands now.”

When your teammate touches gently, press **G**. HARE says **“Perfect. Soft hands.”**
These are presenter events; no bump/ear-touch sensors or physical ear servos are
connected. Duplicate or out-of-order cues cannot repeat or skip the sequence.

Say: **“HARE shows the effect, then gives the learner a way to fix it at once.”**

## Close and complete hardware fallback

Select **Closing slide** to show **“Learner walked away → hop-counting. Same
lesson, new shape.”** The presenter cue contains the ADHD-focused statement and
no-diagnosis qualification. Credit Devin, Codex, ElevenLabs, and Deepgram.
This Python server uses Unitree WebRTC directly; it does not run a dimOS process.
Do not say this server runs on dimOS unless you separately integrate that runtime.

Select **Hardware backup** to show **“It sees. It moves. It cares.”** Use the
three capability statements in the presenter cue. **Caption rehearsal** runs
all three stories without audio providers, a robot, or microphone; captions
advance automatically, while counts and touch events use the presenter keys.

## Controls and limits

| Key | Meaning |
| --- | --- |
| `F` | Apply the count currently entered in Fallback block count |
| `L` | Cue the learner walking away in the red-block mission |
| `B` | Hard-bump presenter cue during Soft Hands |
| `G` | Gentle-touch presenter cue after HARE requests it |
| `Space` | STOP ALL |

Letter shortcuts do not run while typing or holding modifier keys; repeats are
ignored. Keep the operator tab focused. STOP, focus loss, controller loss, or an
audio failure cancels the active sequence. Hardware mode also stops on robot
connection loss. A stale camera blocks any next physical jump even if a fallback
count was entered. An already accepted firmware motion may still finish.

The camera AI has **speak** and **listen** tools alongside its existing movement
tools. The exact schema and dispatch map are at `/api/ai/tools` and in
[AI_TOOLS.md](AI_TOOLS.md). The scripted demos use deterministic lesson transitions;
the model cannot manufacture a touch event, fallback count, or physical completion.
