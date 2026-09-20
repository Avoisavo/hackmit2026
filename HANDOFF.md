# robot dog face — handoff

## status: working
Board IP: `10.254.159.201:8080` (HackMIT.2026 Wi-Fi). Confirmed live just now — `curl http://10.254.159.201:8080/health` → `{"ok": true, "faces": 1}`.

## what's running on the board
- boots with power only, no keyboard needed (autologin configured)
- desktop autostarts `deploy/kiosk.sh` → starts `server.py` → opens chromium fullscreen on the face
- server listens on `0.0.0.0:8080`, reachable from any device on the same Wi-Fi

## control it
```
curl -X POST http://10.254.159.201:8080/emote -d '{"name":"happy","hold":3}'
```
`hold` in seconds (0 = stays until next call). Emotes: `neutral happy excited curious sad sleepy surprised angry love boot`

Or open **`tools/dashboard.html`** locally — 10 buttons, keys `1`-`9`/`0`, activity log. Board IP is pre-filled in the host field.

## if the IP changes
adb into it and re-check:
```
~/Library/Android/sdk/platform-tools/adb shell 'ip -4 addr show wlan0 | grep inet'
```
Only reachable via adb when USB-C is plugged into a computer, not the display dongle.

## known gotchas (already solved, here if it breaks again)
1. **No HDMI port on the board** — video is USB-C DisplayPort Alt Mode through a powered dongle. Dongle needs its own PD power in or the board browns out.
2. **Board takes ~3.5 min to boot** — LED matrix heartbeat = ready.
3. **CORS** — `server.py` sends `Access-Control-Allow-Origin: *` and handles `OPTIONS` preflight. Needed for `dashboard.html` (different origin) to reach the board. If a future page can't POST, check this first.
4. **No sudo password known** — root access on the board goes through `docker run --privileged` (arduino user is in the `docker` group). Used once already to set up autologin.
5. **`/tmp` doesn't survive reboot** — any setup script must live under `/home/arduino/robotdog-face/`, not `/tmp`.

## not done yet
- Go2 integration — user mentioned Wi-Fi APs `Go2_61331_29d4be72` / `Go2_60968_942f877d` nearby. Bridge from Go2 SDK state → `/emote` calls not built.
- Nothing committed to git yet.

## key files
```
server.py              stdlib HTTP server + SSE + /emote API + CORS
web/face.js             eye renderer, 10 emotes as parameter sets
web/app.js               SSE client, keyboard/touch control
tools/dashboard.html    remote control panel (this session's last addition)
tools/gallery.html      all emotes side by side, for tuning
deploy/kiosk.sh          starts server + launches chromium kiosk on boot
deploy/board-autologin.sh  one-time root setup (already run)
deploy/DISPLAY.md        panel troubleshooting if screen goes black
README.md                full docs
```

## Expression redesign experiment — Study 02

- Local `/lab` studio: ten redesigned moods, Original/Study 02 toggle,
  personality slider, cursor attention, motion toggle, and 24-second demo.
- Original kiosk is still the default. Opt in using
  `/?design=expressive&bare=1&energy=0.65`; existing SSE `/emote` control works.
- Lab is a standalone preview and sends no commands to the board.
- New files: `web/expressive.js`, `web/lab.js`, `web/lab.css`, `tools/lab.html`.
- Shared renderer changes are limited to injectable poses, a details hook,
  per-eye modulation index, and optional fixed offscreen buffers.
- Reduced motion defaults to still poses; explicit moods do not drift into sleep.
- State/geometry checks: `node tools/verify-face.cjs`.
- Not deployed to the board. UNO Q frame rate and physical panel readability
  still need hardware validation before changing the kiosk URL.
- Browser-verified on desktop and 390px mobile: all ten selections, original/new
  switch, still mode, keyboard shortcuts, personality endpoints, and complete
  demo returning to neutral; no captured console warnings/errors. Experimental
  panel connected to SSE locally. Renderer checks passed.
- Preview server for this session: `http://127.0.0.1:8081/lab`.

## Twinkle labv2 — kindergarten face pack draft

- Open `/labv2` (this session: `http://127.0.0.1:8082/labv2`). Separate from `/lab`.
- Eight exact names: Ready, Watching, Encourage, Thinking, Go, Celebrate, Rest,
  Soft confused. No angry/sad/scoring reactions; waiting stays Ready indefinitely.
- Puppy face pack with still thumbnails, motion toggle, small-screen check,
  face-only display, and the blue-block 2 + 1 = 3 story.
- Interactive hint / more time / movement branches, plus break/help/blocked-view
  scenarios. Local simulation only; no camera, speech, or board control.
- Implementation: `web/twinkle.js`, `web/labv2.js`, `web/labv2.css`,
  `tools/labv2.html`; `/labv2` route added to `server.py`.
- Full face language / behavior notes: `docs/twinkle-face-pack.md`.
- Check: `node tools/verify-twinkle.cjs`. Existing renderer checks also pass.
- Not deployed. Board API and kiosk still use their previous emote names.
- Verified in browser: all eight faces, keyboard selection, each help branch,
  positive break and blocked-view scenarios, full automatic story returning to
  Ready, completed equation, static poses, 390px mobile with no horizontal
  overflow, and face-only 1024×600 display. No captured console errors/warnings.


### labv2 revision — abstract light character

The literal puppy face was replaced at the user's request. The current design is
two warm light shapes: no ears, nose, mouth, cheeks, pupils, or thought bubbles.
All eight names and story branches remain. Shape, spacing, gaze, tilt, and timing
carry expression; only Celebrate adds a single tiny sparkle. Updated face-pack
notes describe the current direction. This supersedes the puppy-face description
above. Preview remains `http://127.0.0.1:8082/labv2`.


### labv2 polish — restore the original lab's shiny, curious character

Per user preference, labv2 now borrows `/lab`'s rounded-square amber eyes, glass
highlights, stronger bloom, and dark backdrop. Added irregular idle glances,
cursor attention in the lab, playful Ready/Thinking tilts, and arrival bounce.
Watching still focuses down at the mat; Rest stays quiet. Abstract two-eye design
and all eight kindergarten emotes remain. Original `/lab` is unchanged.
