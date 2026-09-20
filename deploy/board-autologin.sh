#!/bin/sh
# Configures the UNO Q to auto-start the desktop (and the face) with no login
# prompt. Runs inside a host-root chroot; see the docker command in README.
set -e
U=arduino
groupadd -f autologin
groupadd -f nopasswdlogin
usermod -aG autologin,nopasswdlogin "$U"
mkdir -p /etc/lightdm/lightdm.conf.d
F=/etc/lightdm/lightdm.conf.d/50-autologin.conf
echo "[Seat:*]"                    >  "$F"
echo "autologin-user=$U"           >> "$F"
echo "autologin-user-timeout=0"    >> "$F"
echo "autologin-session=xfce"      >> "$F"
echo "autologin configured; restarting lightdm"
systemctl restart lightdm
