# Getting a picture on the Wisecoco 7"

The UNO Q has no HDMI socket. Video leaves the board over its single USB-C
port as DisplayPort Alt Mode (handled by the onboard ANX7625), so the chain is:

    UNO Q  --USB-C-->  powered dongle  --HDMI-->  Wisecoco 7"
                            ^
                            +-- PD power in (required)

Use a dongle with power delivery passthrough. Arduino's docs note that any
brand works **except** Apple's. Do not power the board from a plain USB-C-to-HDMI
cable with no PD input: the board browns out under load.

**The face does not care what resolution you end up at.** It is drawn in a
1000x600 design space and scaled to fit, so 1024x600 and 1280x800 both look
correct. You only need to get *a* signal.

## If the screen stays black

There is a known report of the UNO Q producing no signal over DP Alt Mode when
the attached panel advertises an unusual preferred mode, which is exactly what
small 7" panels do. Work through these in order.

### 1. Confirm the board sees the panel at all

```sh
for c in /sys/class/drm/card*-*/; do
  printf '%s %s\n' "$c" "$(cat "$c/status" 2>/dev/null)"
done
```

A `connected` line for a `DP` connector means the link is up and the problem is
mode selection. `disconnected` everywhere means the dongle or cable is the
problem — try the dongle on a laptop first to prove it does video at all.

### 2. Read what the panel is asking for

```sh
sudo apt install -y edid-decode
cat /sys/class/drm/card0-DP-1/edid | edid-decode
```

Note the preferred timing. Wisecoco 7" panels are usually 1024x600@60 or
1280x800@60 — check the label, they are not interchangeable.

### 3. Force the mode from userspace (X11, easiest to try)

```sh
cvt 1024 600 60
# -> Modeline "1024x600_60.00"  49.00  1024 1072 1168 1312  600 603 613 624 -hsync +vsync

xrandr --newmode "1024x600_60.00" 49.00 1024 1072 1168 1312 600 603 613 624 -hsync +vsync
xrandr --addmode DP-1 "1024x600_60.00"
xrandr --output DP-1 --mode "1024x600_60.00"
```

Run `xrandr` on its own first to get the real connector name — substitute it
for `DP-1` above. If `xrandr` reports "Can't open display", the session is
Wayland; use `wlr-randr` or skip to step 4.

To make it stick, put those three commands at the top of
`deploy/kiosk.sh`, before the browser launches.

### 4. Force the mode at the kernel level (most reliable)

Add to the kernel command line:

```
video=DP-1:1024x600@60e
```

The trailing `e` forces the output enabled even if EDID negotiation failed —
that is the bit that rescues a panel the board refuses to light up. Where the
cmdline lives depends on the boot setup; check `/etc/default/grub`,
`/boot/firmware/`, or `/boot/` on your image, and confirm afterward with
`cat /proc/cmdline`.

### 5. Override the EDID entirely (last resort)

If the panel's EDID is simply wrong, supply your own:

```sh
sudo mkdir -p /lib/firmware/edid
# place a known-good binary EDID at /lib/firmware/edid/panel.bin, then add to cmdline:
#   drm.edid_firmware=DP-1:edid/panel.bin
```

## Rotation

If the panel is mounted sideways in the dog's head:

```sh
xrandr --output DP-1 --rotate left     # or right / inverted
```

Add it to `kiosk.sh` next to the mode commands.

## Blanking

`kiosk.sh` already runs `xset s off -dpms s noblank`. If the face still blanks,
the session's own screensaver is overriding it — check the desktop's power
settings, or install `caffeine`.
