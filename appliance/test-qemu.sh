#!/usr/bin/env bash
# Boot a built appliance ISO in QEMU and forward the console to the host.
#
#   ./test-qemu.sh out/dcc-appliance-*.iso
#
# Then open http://localhost:8000 on the host. Requires qemu (qemu-full).
set -euo pipefail

ISO="${1:-}"
if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
  echo "usage: $0 /path/to/dcc-appliance.iso" >&2
  exit 1
fi

if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
  echo "error: qemu-system-x86_64 not found. install: sudo pacman -S qemu-full" >&2
  exit 1
fi

ACCEL=()
if [ -w /dev/kvm ]; then ACCEL=(-enable-kvm); else echo "note: /dev/kvm not writable; running without KVM (slow)"; fi

echo "Booting $ISO with the console forwarded to http://localhost:8000 …"
exec qemu-system-x86_64 \
  -m 4096 -smp 2 "${ACCEL[@]}" \
  -cdrom "$ISO" -boot d \
  -netdev user,id=n0,hostfwd=tcp::8000-:8000 \
  -device virtio-net-pci,netdev=n0 \
  -vga virtio
