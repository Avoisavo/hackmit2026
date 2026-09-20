# HARE — demo script

**HARE** — Hands-on Adaptive Real-world Education.

A robot companion that runs short physical learning games. It checks a real
answer with a camera, and it changes the activity when a child stalls.

Made for preschoolers. It helps every young child, and helps most the children
who find sitting still hardest, including children with ADHD.
It does not diagnose anything.

---

## The three cases

| # | Case | What it proves | Time |
|---|---|---|---|
| 1 | **Count and Check** | HARE checks a real, physical answer | 45 s |
| 2 | **Run, Play, Teach Again** | HARE changes the shape of the lesson | 60 s |
| 3 | **Soft Hands** | HARE teaches care without scolding | 25 s |

Total: about 2 minutes 10 seconds, plus a 20-second close.

---

## Before you start

| Item | Setup |
|---|---|
| Mat | Plain, one colour, no pattern |
| Blocks | Large, high contrast, two colours only |
| HARE | Standing, charged, ears up |
| Face | Board reachable, `/health` returns `rabbit-v1-glossy` |
| Slide behind | "HARE — Hands-on Adaptive Real-world Education" |
| People | One person speaks. One person runs the laptop |
| Floor | Mark a clear area. Keep judges outside it |

Check the face before you walk on:

```sh
curl http://<board-ip>:8080/health
```

The board IP and recovery steps are in `HANDOFF.md`.

---

## Use case 1 — Count and Check

**Proves:** HARE checks a real, physical answer.

**Say first:** "HARE checks a real answer, not a tap on a screen."

| # | Action | Face |
|---|---|---|
| 1 | HARE says: "Put three blue blocks on the mat." | `Ready` |
| 2 | Your teammate places **two** blocks | `Watching` |
| 3 | The camera counts two. The screen shows **2** | `Watching` |
| 4 | HARE says: "You have two. How many more do we need?" | `Encourage` |
| 5 | Your teammate adds one block | `Watching` |
| 6 | HARE hops. The screen shows **2 + 1 = 3!** | `Celebrate` |

**Fallback:** If the camera fails, press your fallback key. The screen shows the
count. Keep talking.

---

## Use case 2 — Run, Play, Teach Again

**Proves:** HARE changes the shape of the lesson instead of pushing on.

**Say first:** "Watch what happens when the child stalls."

| # | Action | Face |
|---|---|---|
| 1 | HARE says: "Put five red blocks on the mat." | `Ready` |
| 2 | Your teammate stalls, then walks away | `Thinking` |
| 3 | HARE says: "You need to move. Let's move together!" | `Encourage` |
| 4 | HARE hops away and says: "Catch me!" | `Go` |
| 5 | Your teammate chases HARE. HARE stops | `Go` |
| 6 | HARE says: "I hopped. Count my hops!" | `Watching` |
| 7 | HARE hops three times | `Go` |
| 8 | Your teammate says: "Three." | `Encourage` |
| 9 | HARE says: "Three! Now add two more." HARE hops twice | `Go` |
| 10 | Your teammate says: "Five." | `Celebrate` |
| 11 | HARE says: "Five. Same as five red blocks. Let's go back." | `Ready` |
| 12 | Your teammate returns and finishes the block mission | `Celebrate` |

**Say after:** "The child never escaped the maths. The maths changed shape.
Blocks became hops."

Say that line clearly. It is your strongest teaching point.

**Safety:** HARE runs away. HARE never chases the child.

**Fallback:** No space to run? HARE hops in place. Keep steps 6 to 11.

---

## Use case 3 — Soft Hands

**Proves:** HARE teaches care without scolding.

**Say first:** "HARE is a creature. The child practises care on HARE."

| # | Action | Face |
|---|---|---|
| 1 | Your teammate bumps HARE hard | `Soft confused` |
| 2 | HARE says: "Ouch, that was too hard. Softer, please." | `Soft confused` |
| 3 | HARE says: "Other people and animals feel pain too." | `Thinking` |
| 4 | HARE says: "Show me soft hands now." | `Watching` |
| 5 | Your teammate touches HARE's ear gently | `Watching` |
| 6 | HARE says: "Perfect. Soft hands." | `Celebrate` |

**Say after:** "HARE shows the effect, then gives the child a way to fix it
at once."

**Safety:** Use your own teammate. Never invite a judge to bump the robot.

**Note:** The face pack has no angry face and no sad face. That is deliberate.
HARE never scolds a child.

---

## The close — 20 seconds

1. Show the dashboard slide:

   > "Child walked away → HARE switched to hop-counting. Same lesson, new shape."

2. Say the key line:

   > "HARE is made for preschoolers. It helps every child, and helps most the
   > ones who find sitting still hardest. It adapts the mission, not the child.
   > It does not diagnose anything."

3. Say the build line:

   > "We built HARE with Devin and Codex. It runs on dimOS, with ElevenLabs and
   > Deepgram for voice."

---

## Which sponsor sees what

| Sponsor | Where it appears |
|---|---|
| Dimensional | The hops in case 1 step 6, and case 2 steps 4 to 9 |
| ElevenLabs | Every line HARE speaks |
| Deepgram | Case 2 steps 8 and 10 |
| OpenAI | Case 1 step 4, the explanation |
| Arduino | Case 3, the pressure sensor reading hard and soft |
| Cognition | Say "we built this with Devin" in the close |

Point at each one as it happens. Judges tick boxes fast.

---

## What HARE must never claim

Say it correctly or a judge will stop you.

| Do not say | Say instead |
|---|---|
| "HARE detects when a child hurts an animal" | "HARE teaches soft hands and asking first" |
| "HARE corrects bad behaviour" | "HARE turns rough contact into the next mission" |
| "HARE teaches ethics" | "HARE models gentle care. The child practises on HARE" |
| "HARE feels pain" | "HARE's ears wobble, so the child sees the effect" |
| "HARE measures attention" | "HARE asks the child what they need" |
| "HARE detects ADHD" | "HARE is for preschoolers, and helps most those who find sitting still hardest" |

You cannot detect cruelty or attention with a camera. Do not claim it.

---

## Seven rules that save demos

1. Rehearse under the real room lighting. Computer vision fails when light changes.
2. Lock the camera white balance and exposure. Do not use auto.
3. Add a keyboard fallback for every step. One keypress advances the flow.
4. Record a full backup video. Play it if the hardware dies.
5. Never let a judge place the blocks. Use your teammate.
6. Charge the robot between every run. Four-legged robots drain fast.
7. Test the voice over room noise. Hackathon halls are loud.

---

## Operator cheat sheet

Drive the face by hand from any device on the same Wi-Fi.

```sh
BOARD=http://<board-ip>:8080

curl -X POST $BOARD/emote -d '{"name":"Ready","hold":0}'
curl -X POST $BOARD/emote -d '{"name":"Watching","hold":0}'
curl -X POST $BOARD/emote -d '{"name":"Encourage","hold":3}'
curl -X POST $BOARD/emote -d '{"name":"Thinking","hold":0}'
curl -X POST $BOARD/emote -d '{"name":"Go","hold":0}'
curl -X POST $BOARD/emote -d '{"name":"Celebrate","hold":3}'
curl -X POST $BOARD/emote -d '{"name":"Rest","hold":0}'
curl -X POST $BOARD/emote -d '{"name":"Soft confused","hold":2}'
```

`hold` is in seconds. `0` holds until the next call.

Or open `tools/dashboard.html` on your laptop. It gives you buttons, keys `1`
to `9` and `0`, and an activity log.

Reset to idle before you walk on stage:

```sh
curl -X POST $BOARD/emote -d '{"name":"Ready","hold":0}'
```

---

## If everything breaks

Rehearse these three lines. They carry the pitch with no hardware at all.

1. **It sees.** HARE checks a real answer with a camera.
2. **It moves.** HARE turns blocks into hops when the child stalls.
3. **It cares.** HARE teaches soft hands, and never scolds.

---

## The name

HARE takes its name from TWICE — "Hare Hare". In Japanese, *hare* means clear
skies. Do not explain this on stage. Just say it is a hare.
