#!/usr/bin/env bash
# Runs inside the build chroot (via mkarchiso) to finish the appliance image.
set -euo pipefail

echo "[customize] building the console virtualenv…"
python -m venv /opt/directory-console/venv
/opt/directory-console/venv/bin/pip install --upgrade pip wheel
/opt/directory-console/venv/bin/pip install --no-cache-dir -r /opt/directory-console/requirements.txt

echo "[customize] enabling services…"
systemctl enable NetworkManager.service
systemctl enable dcc-provision.service
systemctl enable samba-ad-dc.service
systemctl enable dcc-console.service
systemctl enable getty@tty1.service
# Kiosk is installed but off by default (works headless too):
#   systemctl enable dcc-kiosk.service && systemctl set-default graphical.target
systemctl disable systemd-resolved.service 2>/dev/null || true

echo dcc > /etc/hostname
echo "127.0.0.1 dcc localhost" > /etc/hosts

# Tell Samba/dnsmasq not to fight a host resolver; Samba's internal DNS answers locally.
printf 'nameserver 1.1.1.1\n' > /etc/resolv.conf

echo "[customize] done."
