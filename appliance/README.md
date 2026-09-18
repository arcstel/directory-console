# Directory Control Center — Appliance (Tier 2)

A bootable Arch Linux ISO that comes up as a self-contained identity appliance:
a **Samba AD DC** plus the **Directory Control Center** console, with a first-run
**provisioning wizard**. Boot the ISO, open `http://<appliance>:8000`, create your
domain, and start managing it — no Docker, no cloud.

## What boots

```
 power on
   → getty@tty1 (autologin) prints the appliance banner with URLs
   → dcc-provision.service   (AUTO_PROVISION, or waits for the wizard)
   → samba-ad-dc.service     (Samba AD DC, internal DNS)
   → dcc-console.service     (uvicorn → http://<host>:8000)
   → [optional] dcc-kiosk.service (cage + chromium fullscreen)
```

First boot with the shipped config (`AUTO_PROVISION=false`) lands on the **setup
wizard** at `http://<host>:8000/setup.html`. Prefer zero-touch? Set
`AUTO_PROVISION=true` in `/etc/dcc/dcc.conf` (or edit the profile before building)
and the domain is created automatically at boot.

## Layout

| Path | Purpose |
| --- | --- |
| `build.sh` | Stages `../backend` into the profile and runs `mkarchiso`. |
| `test-qemu.sh` | Boots a built ISO in QEMU, forwarding the console to `localhost:8000`. |
| `archiso/profiledef.sh` | ISO metadata, boot modes (BIOS + UEFI), squashfs settings. |
| `archiso/packages.x86_64` | Packages baked into the image (samba, python, kiosk, boot). |
| `archiso/airootfs/` | Files overlaid into the live system. |
| `archiso/airootfs/etc/dcc/` | `dcc.conf` (provisioning inputs) and `dcc.env` (console env). |
| `archiso/airootfs/usr/local/bin/` | `dcc-provision`, `dcc-seed`, `dcc-banner`. |
| `archiso/airootfs/root/customize_airootfs.sh` | Build-chroot hook: venv + enable services. |

## Build

```bash
sudo pacman -S --needed archiso xorriso squashfs-tools mtools libisoburn
cd appliance
sudo ./build.sh
```

Output lands in `appliance/out/`. The console virtualenv is built inside the
image, so the build needs network access to PyPI.

## Run in QEMU

```bash
./test-qemu.sh out/dcc-appliance-*.iso
# then open http://localhost:8000
```

> **Persistence:** a plain live ISO is ephemeral — the provisioned domain lives in
> RAM and is rebuilt on each boot. For a persistent appliance, install the ISO to
> disk (or add an `archiso` persistence partition) so `/var/lib/samba` survives.

## Configure before building

Edit `archiso/airootfs/etc/dcc/dcc.conf`:

```ini
DOMAIN=EXAMPLE
REALM=EXAMPLE.LOCAL
ADMIN_PASS=Passw0rd!2026
DNS_FORWARDER=1.1.1.1
SEED=true
AUTO_PROVISION=false   # true = hands-off boot; false = web wizard
```

## Enable the graphical kiosk (optional)

```bash
systemctl enable dcc-kiosk.service
systemctl set-default graphical.target
```

Needs a display/GPU (virtio-gpu in QEMU is fine). Leave it off to run headless
and manage over the network.

## Status

This is the first cut of Tier 2: profile, services, provisioner, seed, and wizard
are in place and syntax-checked. It has **not** been built into an ISO in this
environment yet (that needs root + the tools above). Next: build + QEMU smoke
test, then a Calamares "install to disk" path for a persistent appliance.
