# Rabbit emotion display

The default display now uses the warm white rabbit design: floating eyes,
pink inner ears, natural blue irises and dark pupils, a pink nose, soft blush,
and the lowered mouth with two ivory front teeth. The neon treatment has been removed.
The renderer is procedural Canvas 2D, inspired by the approved concept;
it is not a pre-rendered 3D image. No additional dependencies are needed.

## Run the rabbit

```sh
python3 server.py
```

- Face: http://localhost:8080/?bare=1
- Ten-emotion gallery: http://localhost:8080/rabbit-gallery.html
- Still preview: http://localhost:8080/?emote=happy&link=0&still=1
- Original design: http://localhost:8080/?design=original

Press 1–9 and 0 for the ten moods, tap the face to cycle, and press F for
fullscreen. The existing `/emote` HTTP API and hold durations still work. Twinkle controller
names are mapped to rabbit moods (Ready→neutral, Watching/Thinking→curious,
Encourage→happy, Go→excited, Celebrate→love, Rest→sleepy, Soft confused→surprised).
The old Twinkle panel remains available at `/twinkle`.
The gallery has a motion toggle; reduced-motion preferences are respected.

| Mood | Rabbit expression |
| --- | --- |
| neutral | Open glossy eyes, relaxed floppy ears, small bunny smile |
| happy | Raised lower lids, brighter cheeks, wider smile |
| excited | Larger eyes, bouncing motion, perked ears, open smile |
| curious | Uneven eyes, one tilted ear, inquisitive head motion |
| sad | Inner eye corners lifted, drooping ears, subdued cheeks |
| sleepy | Heavy lids, relaxed ears, slow breathing |
| surprised | Tall wide-open eyes, raised ears, rounded open mouth |
| angry | Inward slanted lids, tense ears, tight mouth |
| love | Warm white heart-shaped eyes, blushing cheeks, gentle sway |
| boot | Dim ears and mouth, slim illuminated eye slits |

## Code and checks

`web/rabbit.js` contains the new renderer, pose parameters, ear shapes,
soft material shading, mouth and teeth. It extends `web/expressive.js` and uses
`web/face.js` for the animation and control contract. `web/app.js` selects
the rabbit by default, and `web/index.html` loads it.

```sh
node tools/verify-face.cjs
node tools/verify-twinkle.cjs
```

Desktop browser appearance has been checked. Actual frame rate and brightness
on the UNO Q / physical LCD still need a hardware check. The existing Next.js
scaffold is separate from this Python-served display.

---

## Previous project documentation

# robot dog face

Animated vector eyes for a robot dog, on an Arduino UNO Q driving a 7" HDMI
panel. Ten emotes, an idle loop that keeps the face alive between them, and an
HTTP API so anything on the network can change the dog's mood.

![ten emotes](docs/gallery.png)

## Run it

```sh
python3 server.py            # no dependencies, stdlib only
```

- <http://localhost:8080/> — the face
- <http://localhost:8080/labv2> — Twinkle kindergarten face pack and blue-block story
- <http://localhost:8080/lab> — experimental expression studio, with original/new comparison
- <http://localhost:8080/gallery> — every emote side by side, for tuning poses

Keys on the face page: `1`-`9`,`0` switch emotes, `h` toggles the legend,
`f` fullscreen. Tapping the screen cycles emotes, for touch panels with no
keyboard nearby.

## Control it

```sh
curl -X POST http://<board-ip>:8080/emote -d '{"name":"happy","hold":3}'
curl "http://<board-ip>:8080/emote?name=curious"      # for address bars
curl http://<board-ip>:8080/emotes                     # list them
curl http://<board-ip>:8080/health                     # is a face connected?
```

`hold` is optional: after that many seconds the face melts back to `neutral`.
Omit it and the emote stays until something else changes it.

Emotes: `neutral` `happy` `excited` `curious` `sad` `sleepy` `surprised`
`angry` `love` `boot`

The face page reconnects to the server on its own, forever. If the brain
restarts, the dog keeps blinking instead of going black.

## Put it on the board

The UNO Q's single USB-C port is taken by the display dongle, so copy over
Wi-Fi rather than USB:

```sh
scp -r . <user>@<board-ip>:~/robotdog-face
ssh <user>@<board-ip> 'sudo sh ~/robotdog-face/deploy/install.sh'
```

That installs the server as a systemd service (starts at boot, restarts if it
dies) and adds a desktop autostart entry that launches the face fullscreen in
Chromium. Reboot and the dog wakes up with a face.

If the screen stays black, read [`deploy/DISPLAY.md`](deploy/DISPLAY.md) — small
7" panels are the exact case that trips up the UNO Q's DisplayPort Alt Mode
handling, and that file has the fix in escalating order.

## Changing the face

Everything visual is in `web/face.js`.

An emote is a set of eye parameters, nothing more — size, corner radius, tilt,
how far the upper lid closes, at what angle, and how much the lower lid arcs.
Switching emotes tweens between parameter sets; the overshoot on that tween is
what makes the dog read as alive rather than as a slideshow.

```js
happy: { eye: { h: 152, y: 14, r: 64, lidLCurve: 0.60 }, ease: 'back', dur: 0.28 },
```

To add one, add an entry to `EMOTES` and the same name to `EMOTES` in
`server.py`. Open `/gallery` to see it next to the others.

- `ease: 'back'` overshoots — use it for perky moods.
- `ease: 'soft'` settles without a bounce — use it for `sad` and `sleepy`.
- `lidUTilt` positive pulls the inner corners **down** (angry); negative pulls
  them up (sad).
- Per-side `l:`/`r:` overrides are taken literally, with no mirroring, so a
  head-tilt can lean both eyes the same way.

Eye color is `DEFAULT_COLOR` at the top of `face.js`, overridable per-load with
`?color=%2300E5FF` and per-emote with a `color:` field (`angry` and `love`
already use it).

## URL flags

| flag | effect |
|---|---|
| `?bare=1` | hides the legend and status line — what the kiosk uses |
| `?emote=angry` | pin one pose, for checking a face on the real panel |
| `?idle=0` | freeze the idle loop (no blinking, no saccades) |
| `?link=0` | skip the control channel; also the only way to screenshot the page headlessly, since an open SSE stream never reaches network-idle |
| `?color=%23FF5C8A` | override the eye color |

## Expression study 02 (experimental)

Open `/lab` and press **Meet the dog** for a 24-second encounter. All ten moods
have new silhouettes and distinct motion: curious tilts, excited bounces,
heavy sleepy blinks, and quieter happy/love sways. A small mouth, brows, and
cheek marks reinforce expressions at panel size. The personality slider
scales expressive motion; zero keeps a small amount of breathing and gaze.
Turn **Living motion** off for completely still poses. Reduced-motion system
preferences default to still poses. The original renderer is available in the
same studio for immediate comparison.

The lab runs entirely locally: it does not subscribe to SSE or send board
commands. **Open panel view** carries the chosen design, mood, motion setting,
and energy into a standalone face. The existing `/` and kiosk remain original.
To opt a panel into the new design with normal SSE control, use:

```
/?design=expressive&bare=1&energy=0.65
```

`web/expressive.js` extends the shared `Face` renderer without new dependencies.
`web/lab.js`, `web/lab.css`, and `tools/lab.html` provide the studio. Existing
emote names and hold semantics are unchanged. Explicit moods no longer become
drowsy with time in the experimental design; only neutral does. The experiment
has not been deployed to or performance-tested on the UNO Q.

Run dependency-free renderer checks with `node tools/verify-face.cjs`.

## Twinkle / labv2 draft

`/labv2` explores a gentle puppy face for a kindergarten learning companion.
It includes Ready, Watching, Encourage, Thinking, Go, Celebrate, Rest, and
Soft confused, plus a playable 2 + 1 = 3 story with hint, more-time, and movement
choices. Use keys 1–8, the motion toggle, and the small-screen check to compare
expressions. `/labv2?panel=1&emote=Ready` opens a face-only preview.

This is a separate local draft; it does not change the board API or kiosk.
See [the face-pack notes](docs/twinkle-face-pack.md) for the expression contract,
scenario mappings, accessibility behavior, and implementation details.

---

## Next.js app scaffold (`app/`)

This repo also contains a separate Next.js app at `app/` (unrelated to the
robot dog face above), bootstrapped with `create-next-app`.

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
