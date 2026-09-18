#!/usr/bin/env bash
# Runs inside the build chroot (via mkarchiso) to finish the appliance image.
set -euo pipefail

echo "[customize] building the console virtualenv…"
python -m venv /opt/janusos/venv
/opt/janusos/venv/bin/pip install --upgrade pip wheel
/opt/janusos/venv/bin/pip install --no-cache-dir -r /opt/janusos/requirements.txt

echo "[customize] enabling services…"
systemctl enable NetworkManager.service
systemctl enable janus-provision.service
systemctl enable samba-ad-dc.service
systemctl enable janus-console.service
systemctl enable getty@tty1.service
# Kiosk is installed but off by default (works headless too):
#   systemctl enable janus-kiosk.service && systemctl set-default graphical.target
systemctl disable systemd-resolved.service 2>/dev/null || true

echo janus > /etc/hostname
echo "127.0.0.1 janus localhost" > /etc/hosts

# Tell Samba/dnsmasq not to fight a host resolver; Samba's internal DNS answers locally.
printf 'nameserver 1.1.1.1\n' > /etc/resolv.conf

echo "[customize] done."
