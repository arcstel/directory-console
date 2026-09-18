#!/usr/bin/env bash
# Build the Janus Directory Console appliance ISO.
#
#   sudo ./build.sh [output-dir]
#
# Requires (root): archiso, xorriso, squashfs-tools, mtools, libisoburn.
# The console backend is staged from ../backend into the profile, then built.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
PROFILE="$HERE/archiso"
OUT="${1:-$HERE/out}"
WORK="${JANUS_WORK:-/tmp/janus-archiso-work}"

if [ "$(id -u)" -ne 0 ]; then
  echo "error: mkarchiso must run as root. Try: sudo $0 $*" >&2
  exit 1
fi

missing=()
for bin in mkarchiso xorriso mksquashfs mcopy; do
  command -v "$bin" >/dev/null 2>&1 || missing+=("$bin")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "error: missing build tools: ${missing[*]}" >&2
  echo "install with: sudo pacman -S --needed archiso xorriso squashfs-tools mtools libisoburn" >&2
  exit 1
fi

echo "==> Staging console backend into the profile"
rm -rf "$PROFILE/airootfs/opt/janusos/app"
mkdir -p "$PROFILE/airootfs/opt/janusos"
cp -r "$REPO/backend/app" "$PROFILE/airootfs/opt/janusos/app"
find "$PROFILE/airootfs/opt/janusos/app" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "$PROFILE/airootfs/opt/janusos/app" -name '*.pyc' -delete 2>/dev/null || true
cp "$REPO/backend/requirements.txt" "$PROFILE/airootfs/opt/janusos/requirements.txt"
chmod +x "$PROFILE/airootfs/usr/local/bin/"* "$PROFILE/airootfs/root/customize_airootfs.sh"

echo "==> Building ISO (work=$WORK out=$OUT)"
mkdir -p "$OUT"
mkarchiso -v -w "$WORK" -o "$OUT" "$PROFILE"

echo
echo "==> Done. Artefacts:"
ls -lh "$OUT"
echo
echo "Test boot:  ./test-qemu.sh \"$(ls -1 "$OUT"/*.iso | head -1)\""
