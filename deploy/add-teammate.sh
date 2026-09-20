#!/bin/sh
# Give a teammate SSH access to the face board.
#
#   sh deploy/add-teammate.sh ~/Downloads/alex_id_ed25519.pub
#   sh deploy/add-teammate.sh "ssh-ed25519 AAAAC3... alex@laptop"
#
# Works over USB (adb) or over Wi-Fi (ssh), whichever is available.
# The teammate makes their key once with:  ssh-keygen -t ed25519
# and sends you the .pub file. Never their private key.
set -e

KEYS_FILE=/home/arduino/.ssh/authorized_keys
[ -n "$1" ] || { echo "usage: sh deploy/add-teammate.sh <pubkey-file | \"ssh-ed25519 AAAA...\">" >&2; exit 1; }

if [ -f "$1" ]; then KEY=$(cat "$1"); else KEY="$1"; fi
case "$KEY" in
  ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*\ *) ;;
  *) echo "that does not look like a public key. it must start with ssh-ed25519 or ssh-rsa." >&2
     echo "did you paste a PRIVATE key by mistake? never share that." >&2; exit 1 ;;
esac

add_cmd="mkdir -p /home/arduino/.ssh && chmod 700 /home/arduino/.ssh && touch $KEYS_FILE && chmod 600 $KEYS_FILE && grep -qF '$KEY' $KEYS_FILE || echo '$KEY' >> $KEYS_FILE; sync; wc -l < $KEYS_FILE"

if command -v adb >/dev/null 2>&1 && adb devices | sed -n '2p' | grep -q device; then
  echo "adding over USB..."
  N=$(adb shell "$add_cmd" | tr -d '\r')
else
  BOARD="${BOARD:?set BOARD=<board-ip> when the cable is not plugged in}"
  echo "adding over ssh to $BOARD..."
  N=$(ssh -p "${SSH_PORT:-2222}" "arduino@$BOARD" "$add_cmd" | tr -d '\r')
fi

echo "done. $N key(s) now authorised."
echo
echo "tell your teammate to run:"
echo "  ssh -p ${SSH_PORT:-2222} arduino@<board-ip>"
echo "  sh deploy/face.sh status"
