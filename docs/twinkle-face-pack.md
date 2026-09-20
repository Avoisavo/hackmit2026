# Twinkle face pack — labv2 draft

Twinkle is a friendly kindergarten learning companion. Its face responds to the
situation; it never scores, diagnoses, or judges a child. This draft is a visual
and interaction prototype, not a camera, speech, or robot integration.

Open `/labv2`. Select a face, press keys 1–8, or play the roughly 31-second blue-block
story. The help choices and scenario shortcuts can interrupt the story at any time.
`/labv2?panel=1&emote=Ready` is a face-only display; `&motion=0` freezes it.
Names containing spaces must be URL-encoded. `&result=1` adds the 2 + 1 = 3 equation.

| Exact emote name | Visual signal | Use |
|---|---|---|
| Ready | Two soft open lights, small breaths and glances | Start, between missions, waiting patiently |
| Watching | Wider, lower lights angled toward the mat by position | Watching blocks arrive on the mat |
| Encourage | Small smiling ribbons and a single gentle nod | Partial progress, supportive response after help |
| Thinking | One light perks up; asymmetric gaze shifts aside | Offering a hint, time, or movement |
| Go | Both lights stretch tall and rise, with a brief eager bounce | Movement invitation |
| Celebrate | Wide beaming curves and one tiny sparkle | Completed discovery |
| Rest | Low, soft resting ribbons and slow breathing | A positive, child-requested break |
| Soft confused | The pair tips sideways, slightly out of step | Unclear view or input; no blaming the child |

The revised direction is abstract: two glossy amber light shapes, with no ears,
nose, mouth, cheeks, pupils, or thought bubbles. The physical robot already
supplies the dog silhouette; the display supplies its emotional character.
Soft square silhouettes, clipped glass highlights, and amber bloom recall the
original `/lab`. Expressions use size, spacing, curvature, tilt, and timing.
Irregular glances and cursor attention add presence; Watching stays on the mat
and Rest stays quiet. Ready and Thinking have a small playful sway. A shared path morphs
between open shapes and closed ribbons without crossfading. Encourage stays
quieter than Celebrate; only Celebrate has a tiny sparkle. Thinking and Soft
confused use different asymmetry and tilt. No red/error or shaming treatment.

## Story behavior

Ready → Watching (two blocks) → Encourage (how many more?) → Thinking (choices)
→ Go (movement chosen) → Watching (one added) → Celebrate (2 + 1 = 3).
The equation appears on the main display and in the mat preview. After the automatic
celebration, the face returns to Ready; the mat retains the completed equation.

- Hint: Encourage, count together, then observe the added block and celebrate.
- More time: Ready indefinitely until the operator continues. No countdown.
- Movement: Go, then watch the returned block and celebrate.
- Ask for help: Thinking; a hint or the next step produces Encourage.
- Break: Rest until the operator continues to Ready.
- Mat out of view: Soft confused, then Watching when the operator resumes.
- Face pack selections stop the story and show a clearly labeled expression preview.

## Motion and implementation

`web/twinkle.js` exports `TwinkleFace` and `TwinkleFace.NAMES`. `setEmote(name)`
accepts only the eight exact names and returns false for unsupported inputs.
`setMotion(false)` stops animation and settles the pose. Transitions blend from
the current pose over 480 ms (900 ms for Rest). Go/Celebrate bounce decays after
arrival; Ready never automatically becomes Rest. Thumbnails are still canvases.
System reduced-motion preferences default to still faces. The lab pauses the story
when hidden and stops drawing until visible again.

`tools/labv2.html`, `web/labv2.css`, and `web/labv2.js` provide the studio.
There are no new dependencies, external fonts, image downloads, or network calls
from the lab. `/lab`, the original kiosk, and `/emote` API are unchanged. These
new names are intentionally not wired into the original board API in this draft.

Checks: `node tools/verify-twinkle.cjs` and `node tools/verify-face.cjs`.
Physical display legibility, frame rate on the UNO Q, and interpretation by children
still need real-world evaluation; a small-screen preview is not a distance study.
