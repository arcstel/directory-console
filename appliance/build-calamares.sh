#!/usr/bin/env bash
# Calamares is AUR-only, so build it in a throwaway Arch container and drop the
# package into appliance/localrepo/. build.sh then pulls it into the ISO.
#
#   ./build-calamares.sh          # host just needs docker
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HERE/localrepo"

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker is required (the build runs in an archlinux container)" >&2
  exit 1
fi

echo "==> Building calamares from the AUR (this takes ~15-20 min)"
docker run --rm -v "$HERE/localrepo:/out" archlinux:latest bash -euxo pipefail -c '
  pacman -Syu --noconfirm --needed base-devel git sudo
  useradd -m builder
  echo "builder ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/builder
  chmod 440 /etc/sudoers.d/builder
  sudo -u builder env MAKEFLAGS="-j4" bash -c \
    "cd /tmp && git clone --depth=1 https://aur.archlinux.org/calamares.git && cd calamares && makepkg -s --noconfirm"
  cp /tmp/calamares/calamares-*.pkg.tar.zst /out/
'

echo "==> Refreshing the local repo"
( cd "$HERE/localrepo" && repo-add -q janus-local.db.tar.gz ./*.pkg.tar.zst )
ls -1 "$HERE/localrepo"
