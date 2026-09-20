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
adb shell 'ip -4 addr show wlan0 | grep inet'
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

## Rabbit face — now the default on the board

The rabbit design replaced Twinkle as the display at `/`. Deployed and verified
on the UNO Q over USB (adb). `curl /health` returns `"version": "rabbit-v1-glossy"`.

- New files: `web/rabbit.js`, `tools/rabbit-gallery.html`.
- `web/index.html` loads `rabbit.js`; `web/app.js` picks `RabbitFace` by default.
- `server.py` serves the rabbit at `/`, `/rabbit` and `/classic`. The old Twinkle
  panel stays at `/twinkle`.
- `deploy/kiosk.sh` now opens `/?bare=1`. Set `FACE_URL` to override.
- All eight Twinkle controller names still work and map to rabbit moods.

Other designs: `/?design=original` and `/?design=expressive`.

### adb on a fresh Mac
The old `~/Library/Android/sdk/platform-tools/adb` path is gone. Install it with:
```
brew install --cask android-platform-tools
```

### gotcha: sync after every push
The board lost a whole `adb push` when it rebooted seconds later — the files
came back as 0 bytes, and a `cp -r` backup made just before came back 0 bytes too.
Writes sit in page cache. Always finish with:
```
adb shell 'sync; sync'
```
Then check `find <dir> -type f -size 0 | wc -l` returns 0.

### roll back to Twinkle
```
adb shell 'cp -r /home/arduino/robotdog-face.bak-twinkle/* /home/arduino/robotdog-face/ && sync'
adb shell 'pkill -f robotdog-face/server.py'
adb shell 'cd /home/arduino/robotdog-face && (PORT=8080 setsid python3 server.py >/tmp/robotdog-face.log 2>&1 </dev/null &)'
```

## Working without the USB cable

The board runs full Debian with Wi-Fi, so the cable is only needed once, to
turn wireless access on.

### one-time setup (cable plugged in)
```
sh deploy/wireless-setup.sh
```
It switches adb to TCP/IP on port 5555, enables sshd if the board has it, and
prints the board IP and the reconnect command.

### after that, no cable
```
adb connect <board-ip>:5555
sh deploy/push-face.sh
```
`push-face.sh` pushes every face file, runs `sync`, checks no file landed at
0 bytes, compares checksums, restarts the server, and restarts the kiosk browser.
It works the same over USB or Wi-Fi.

### controlling the face needs no adb at all
`server.py` listens on `0.0.0.0:8080` with `Access-Control-Allow-Origin: *`.
Any device on the same Wi-Fi can drive it:
```
curl -X POST http://<board-ip>:8080/emote -d '{"name":"Celebrate","hold":3}'
```
Or open `tools/dashboard.html` on a laptop and put the board IP in the host field.

### both devices must be on the SAME network
Seen in practice: Mac on `10.189.70.235`, board on `10.254.159.201`. Different
subnets do not route to each other, and venue Wi-Fi often isolates clients from
each other as well. For a demo, put the board and your laptop on a phone hotspot.
Then the IP is stable and no captive portal or client isolation gets in the way.

### Bluetooth
Not worth it. There is no file-transfer path to this board over Bluetooth that
beats Wi-Fi, and pairing adds a failure point during a demo. Use Wi-Fi.

### adb tcpip does not survive a reboot
`adb tcpip 5555` resets to USB mode when the board restarts. sshd does survive.
If `adb connect` stops working after a reboot, plug in once and rerun
`deploy/wireless-setup.sh`.

## Team access over Wi-Fi, with an SSH key

No cable. Each teammate uses their own SSH key.

### why it is set up this way
The board's `adbd` is a Debian package wired to the USB gadget. It cannot listen
on TCP, so `adb tcpip` does nothing here. The system `ssh` service is installed
but disabled, and enabling it needs a root password nobody has.

So the face board runs **its own sshd as the `arduino` user on port 2222**. No
root, no system change. `deploy/kiosk.sh` starts it at login, so it survives a
reboot.

- config:   `/home/arduino/.sshd/sshd_config`
- host key: `/home/arduino/.sshd/host_ed25519`
- log:      `/tmp/sshd.log`
- keys only. Passwords and root login are off.

### add a teammate
They run this once on their own laptop and send you the `.pub` file:
```
ssh-keygen -t ed25519
```
You add it:
```
sh deploy/add-teammate.sh ~/Downloads/their_key.pub
```

### what a teammate then runs
```
export BOARD=<board-ip>            # from `adb shell ip -4 addr show wlan0`

sh deploy/face.sh status           # is the board alive?
sh deploy/face.sh deploy           # copy the face over and restart it
sh deploy/face.sh restart          # restart server + kiosk browser
sh deploy/face.sh emote Celebrate  # drive the face
sh deploy/face.sh emotes           # list every face name
sh deploy/face.sh shell            # a shell on the board
```

### both machines must be on the same Wi-Fi
The board is on the hotspot **"Hong's S24 Ultra"**. A laptop on MIT Wi-Fi cannot
reach it — different subnets, no route. Join the same hotspot first. Check with:
```
curl http://<board-ip>:8080/health
```

### gotcha: nohup AND setsid when restarting over SSH
Starting `server.py` over SSH with `setsid ... &` alone is not enough. sshd kills
it when the command returns and the face goes dark. `deploy/face.sh restart` uses
`nohup setsid`, redirects every stream, and then waits for `/health` before it
exits. Do not simplify that line.

## Reverse tunnel — how the laptop reaches the board on a phone hotspot

The Samsung hotspot isolates its clients. Measured, one-directional:

| From | To | Result |
|---|---|---|
| laptop | phone (gateway) | works |
| board | phone | works |
| **board** | **laptop** | **works** |
| **laptop** | **board** | **blocked** (ARP resolves, packets dropped) |

The board's ports are already open on `0.0.0.0`. Nothing is firewalled on the
board. The phone drops the packets. No app on either machine changes that.

So the board dials **out** and forwards its own ports back to the laptop:

```
laptop:2222 -> board:2222   (ssh)
laptop:8080 -> board:8080   (face server and /emote)
```

### setup, once
1. On the laptop: System Settings > General > Sharing > **Remote Login ON**.
2. Give the board a key and authorise it on the laptop:
```
adb shell 'ssh-keygen -q -t ed25519 -N "" -f /home/arduino/.ssh/id_ed25519'
adb shell 'cat /home/arduino/.ssh/id_ed25519.pub' >> ~/.ssh/authorized_keys
```
3. Tell the board where to dial:
```
adb shell "echo '<you>@<laptop-ip>' > /home/arduino/.sshd/tunnel-target && sync"
```
`deploy/kiosk.sh` starts `deploy/reverse-tunnel.sh` at login, so it comes back
after a reboot and reconnects by itself if the link drops.

### then, with no cable
```
export BOARD=127.0.0.1        # NOT the board IP -- the tunnel lands on localhost
sh deploy/face.sh status
sh deploy/face.sh deploy
```

Verified end to end with adb killed: status, emote, and a full 22-file deploy
plus restart all succeeded, and the tunnel survived the restart.

### limits
- The tunnel lands on **one laptop**. Teammates cannot reach the board directly.
  For whole-team access, use a hotspot that does not isolate clients (an iPhone
  Personal Hotspot does not), and then everyone uses `BOARD=<board-ip>` instead.
- If the laptop's IP changes, update `/home/arduino/.sshd/tunnel-target`.
- The laptop must stay awake and on the same hotspot.

### gotcha: pkill -f matches your own adb shell
`adb shell 'pkill -f reverse-tunnel; nohup ... /path/reverse-tunnel.sh &'` kills
the session, because the command line contains that path. Exit code 143. Use a
bracket pattern (`[r]everse-tunnel`) and put the kill in a separate adb call.
