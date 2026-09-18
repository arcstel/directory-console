# JanusOS — Appliance (Tier 2)

A bootable Arch Linux ISO that comes up as a self-contained identity appliance:
a **Samba AD DC** plus the **Janus Directory Console**, with a first-run
**provisioning wizard**. Boot the ISO, open `http://<appliance>:8000`, create your
domain, and start managing it — no Docker, no cloud.

## What boots

```
 power on
   → getty@tty1 (autologin) prints the appliance banner with URLs
   → janus-provision.service   (AUTO_PROVISION, or waits for the wizard)
   → samba-ad-dc.service     (Samba AD DC, internal DNS)
   → janus-console.service     (uvicorn → http://<host>:8000)
   → [optional] janus-kiosk.service (cage + chromium fullscreen)
```

First boot with the shipped config (`AUTO_PROVISION=false`) lands on the **setup
wizard** at `http://<host>:8000/setup.html`. Prefer zero-touch? Set
`AUTO_PROVISION=true` in `/etc/janus/janus.conf` (or edit the profile before building)
and the domain is created automatically at boot.

## Layout

| Path | Purpose |
| --- | --- |
| `build.sh` | Stages `../backend` into the profile and runs `mkarchiso`. |
| `test-qemu.sh` | Boots a built ISO in QEMU, forwarding the console to `localhost:8000`. |
| `archiso/profiledef.sh` | ISO metadata, boot modes (BIOS + UEFI), squashfs settings. |
| `archiso/packages.x86_64` | Packages baked into the image (samba, python, kiosk, boot). |
| `archiso/airootfs/` | Files overlaid into the live system. |
| `archiso/airootfs/etc/janus/` | `janus.conf` (provisioning inputs) and `janus.env` (console env). |
| `archiso/airootfs/usr/local/bin/` | `janus-provision`, `janus-seed`, `janus-banner`. |
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
./test-qemu.sh out/janus-appliance-*.iso
# then open http://localhost:8000
```

> **Persistence:** a plain live ISO is ephemeral — the provisioned domain lives in
> RAM and is rebuilt on each boot. For a persistent appliance, install the ISO to
> disk (or add an `archiso` persistence partition) so `/var/lib/samba` survives.

## Install to a disk (persistence)

A live boot is ephemeral — the domain lives in RAM. To make JanusOS persistent,
boot the ISO and run the installer:

```bash
janus-install                          # pick a disk interactively
janus-install --target /dev/sda --yes  # scripted, destructive
```

It partitions the target (GPT: ESP + root on UEFI, BIOS-boot + root on BIOS),
unpacks the live system, writes `/etc/fstab`, regenerates the initramfs (dropping
the archiso hooks), installs GRUB, and powers off. Reboot into a persistent
JanusOS; the domain you provision survives reboots.

Unattended install (boot the ISO with these kernel arguments):

```
janus.install=/dev/vda janus.install.yes=1 janus.install.poweroff=1
```

Boot-tested in QEMU: install to disk → provision `ACME.LOCAL` → clean shutdown →
reboot, and the domain plus its 17 seeded identities persist with the console
reconnecting over LDAPS. (Note: shut the VM down cleanly before testing — Samba's
`sam.ldb` is a database, and a hard reset right after provisioning can lose it.)

## Configure before building

Edit `archiso/airootfs/etc/janus/janus.conf`:

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
systemctl enable janus-kiosk.service
systemctl set-default graphical.target
```

Needs a display/GPU (virtio-gpu in QEMU is fine). Leave it off to run headless
and manage over the network.

## Status

Tier 2 builds successfully. A working ISO (`janus-appliance-<date>-x86_64.iso`,
~1.6 GB) is produced with `sudo ./build.sh`, with the console virtualenv baked in
and the `archiso` initramfs hooks present.

**Boot-tested in QEMU** (archiso live image, KVM): console answers on `:8000` in
~30s, the wizard provisions `ACME.LOCAL`, seeds 17 identities, starts Samba, and
the console reads back users and governance over LDAPS.

Requirements discovered the hard way:
- `mkinitcpio-archiso` **must** be in `packages.x86_64` — it provides the
  `archiso` initramfs hook. Without it the image builds but cannot find the
  squashfs at boot.
- Releng's `syslinux/` and `efiboot/` trees plus `mkinitcpio.conf.d/archiso.conf`
  and `mkinitcpio.d/linux.preset` are required in the profile.
- `python-markdown` is required by Samba's forest-update step; provisioning
  fails without it. `python-dnspython` is needed by `samba_dnsupdate`.
- `systemd-firstboot.service` must be masked (and `systemd.firstboot=no` on the
  kernel cmdline), or the live boot stops at an interactive first-boot prompt.
- The NetBIOS domain cannot equal the appliance host name (Samba rejects it);
  the provisioner validates this with a friendly message.

Next: a Calamares "install to disk" path for a persistent appliance.
