# HARE presenter runbook

Run the `dog` branch from `~/Developer/hackmit2026`:

```sh
~/Developer/hackmit2026/robot/start-control-plane.sh
```

Open <http://127.0.0.1:8020/plane>. The header includes **DEMOS · V4**.
The launcher reads the repository's ignored `.env.local`; credentials are not in
Git. Only one server can use port 8020. If it is already running, use that page
or stop that server before starting another. `/controls` retains the working
manual controls and `/vision` retains the independent counting page.

## Before presenting

1. Choose **Whammo 2.0 Speaker** as the Mac's sound output. Click **Use this
   computer's speaker**, then **Play speaker test tone** and **Test ElevenLabs
   voice**. A completed playback event does not prove the speaker was audible.
2. Click **Use this microphone**, select the speaker's microphone in the browser
   prompt, and test with **Listen for 20 seconds**. The mic pauses during HARE's
   speech. Typed answers remain available under **Operator answer fallback**.
3. Connect Go2 for the camera. Add `OPENAI_API_KEY` to `.env.local` and restart
   if it is not already configured. Deepgram and ElevenLabs alone do not provide
   camera analysis. Counted targets include the specified color **and the mat**.
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

Select **1 · Count and Check**. HARE asks for three blue blocks on the mat.
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

Select **2 · Run, Play, Teach Again**. HARE asks for five red blocks. Ten seconds
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

Select **3 · Soft Hands**. Use your own teammate, never a judge. **B** cues the
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
