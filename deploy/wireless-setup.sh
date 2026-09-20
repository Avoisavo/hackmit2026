#!/bin/sh
# RUN ON YOUR MAC, with the board plugged in over USB. One time only.
#
# Sets up key-based SSH so you and your teammates can reach the board over
# Wi-Fi with no cable.
#
#   sh deploy/wireless-setup.sh
#
# NOTE: 'adb tcpip' does NOT work on this board. Its adbd is a Debian package
# wired to the USB gadget and cannot listen on TCP. Enabling the system ssh
# service needs a root password nobody has. So the board runs its own sshd as
# the 'arduino' user on port 2222. No root needed. kiosk.sh starts it at login.
set -e

SSH_PORT=2222
SSHD_DIR=/home/arduino/.sshd
KEYS=/home/arduino/.ssh/authorized_keys

command -v adb >/dev/null 2>&1 || {
  echo "adb not found. install it first:" >&2
  echo "  brew install --cask android-platform-tools" >&2
  exit 1
}

MYKEY_FILE="${MYKEY_FILE:-$HOME/.ssh/id_ed25519.pub}"
[ -f "$MYKEY_FILE" ] || {
  echo "no public key at $MYKEY_FILE" >&2
  echo "make one first:  ssh-keygen -t ed25519" >&2
  exit 1
}
MYKEY=$(cat "$MYKEY_FILE")

echo "waiting for the board over USB..."
adb wait-for-device
echo "connected: $(adb devices | sed -n '2p')"

echo "installing key-only sshd on port $SSH_PORT..."
adb shell "
set -e
mkdir -p /home/arduino/.ssh $SSHD_DIR
chmod 700 /home/arduino/.ssh
[ -f $SSHD_DIR/host_ed25519 ] || ssh-keygen -q -t ed25519 -N '' -f $SSHD_DIR/host_ed25519
chmod 600 $SSHD_DIR/host_ed25519
touch $KEYS && chmod 600 $KEYS
grep -qF '$MYKEY' $KEYS || echo '$MYKEY' >> $KEYS
cat > $SSHD_DIR/sshd_config <<'CFG'
Port $SSH_PORT
ListenAddress 0.0.0.0
HostKey $SSHD_DIR/host_ed25519
PidFile $SSHD_DIR/sshd.pid
AuthorizedKeysFile $KEYS
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
UsePAM no
PrintMotd no
CFG
/usr/sbin/sshd -t -f $SSHD_DIR/sshd_config
pgrep -f 'sshd -f $SSHD_DIR/sshd_config' >/dev/null 2>&1 || \
  (setsid /usr/sbin/sshd -f $SSHD_DIR/sshd_config -E /tmp/sshd.log </dev/null >/dev/null 2>&1 &)
sleep 2
sync
" >/dev/null 2>&1

adb shell "ss -tln 2>/dev/null | grep -q $SSH_PORT && echo ok" | grep -q ok || {
  echo "sshd did not start. check the board:  adb shell 'tail /tmp/sshd.log'" >&2; exit 1; }

IP=$(adb shell "ip -4 addr show wlan0 | awk '/inet /{print \$2}' | cut -d/ -f1" | tr -d '\r')
SSID=$(adb shell 'nmcli -t -f NAME con show --active 2>/dev/null | head -1' | tr -d '\r')
N=$(adb shell "wc -l < $KEYS" | tr -d '\r ')

cat <<TXT

--------------------------------------------------------------------
sshd is listening on port $SSH_PORT. $N key(s) authorised.

board IP:   ${IP:-unknown}
board Wi-Fi: ${SSID:-unknown}

YOUR LAPTOP MUST JOIN THE SAME Wi-Fi as the board. Then unplug and run:

  export BOARD=$IP
  sh deploy/face.sh status
  sh deploy/face.sh deploy

Add a teammate (they send you their .pub file):

  sh deploy/add-teammate.sh their_key.pub

This survives a reboot: deploy/kiosk.sh starts sshd at login.
--------------------------------------------------------------------
TXT
