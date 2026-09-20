# HB face connection from the dog control plane

This integration follows `hb`'s README and the multi-laptop tunnel update
`8deaab1`. The reviewed branch tip was `7c0f0a3`; its recent changes after
`8deaab1` were documentation. The `dog` integration does not change `hb`, deploy
new firmware, restart its kiosk, or replace other laptops' tunnels.

The HB board already runs `server.py`, with the `rabbit-v1-glossy` renderer.
It exposes `GET /health`, `GET /emotes` and `POST /emote`.
The main server sends `{ "name": "Thinking", "hold": 0 }`, using the same eight
names as HB's panel. The board maps them to its rabbit moods. The local operator
preview keeps its existing Twinkle renderer; the expression names are shared.

## Reach it using the existing reverse tunnel

The Samsung hotspot can block laptop-to-board traffic. HB's board dials each
laptop instead, forwarding:

- laptop port **2222** → board SSH port **2222**
- laptop port **8080** → board face HTTP port **8080**

The control plane tries `BOARD_URL` first when present, then
`http://127.0.0.1:8080`, `http://[::1]:8080`, and the existing
`NEXT_PUBLIC_ROBOT_FACE_URL` LAN address from `.env.local`. It verifies the HB
health response before sending an expression. IPv6 is included because HB's
README notes that a tunnel can bind only to `::1`.

Check either address:

```sh
curl --noproxy '*' http://127.0.0.1:8080/health
curl --noproxy '*' 'http://[::1]:8080/health'
```

A working response contains `"ok": true`, `"version": "rabbit-v1-glossy"`, and
`"faces": 1`. HTTP 404 from a plain Python file server is not the HB API.
`faces: 0` means the server is reachable but no display is subscribed. The monitor
shows this distinction. A local preview is not evidence that the board received
an expression.

## One-time setup on this Mac

1. Turn **Remote Login ON** in System Settings → General → Sharing.
2. Authorize the board's existing public SSH key in this account's
   `~/.ssh/authorized_keys`. Use the key supplied by the board owner. Keep
   `~/.ssh` mode 700 and the file mode 600; preserve other authorized keys.
3. Join the same hotspot and obtain the account and address with `whoami` and
   `ipconfig getifaddr en0`.
4. On a teammate's machine that already reaches the board, from the `hb` checkout:

   ```sh
   sh deploy/add-laptop.sh YOUR_USERNAME@YOUR_MAC_IP
   ```

This appends another tunnel target rather than replacing the existing one. If
8080 or 2222 is occupied by another local process, resolve that conflict first;
HB uses `ExitOnForwardFailure=yes`, so a conflicting port prevents its tunnel.
Never kill a process solely because of its port without checking what owns it.

On this session's initial check, Derek's address was `10.254.159.230`, Remote Login
was off, the board public key was absent, no 2222 tunnel was listening, and 8080
belonged to `python3 -m http.server 8080`. IP addresses can change; recheck before
running the add-laptop command. The LAN board address `10.254.159.201:8080` timed
out from this Mac.

Once the tunnel is up, this server detects it automatically within a few seconds.
There is no second panel to start and no need to pair the existing HB kiosk.
If the Mac's IP changes, follow HB's README to update its tunnel target. Keep
other teammates' target lines. Sleep or leaving the hotspot drops only this Mac's
tunnel; it reconnects when the Mac returns.

Optional `/device/face` pairing is still available for a separate browser display.
It does not configure SSH or replace the existing HB board server.
