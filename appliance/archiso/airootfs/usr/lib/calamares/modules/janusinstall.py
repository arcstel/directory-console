# JanusOS custom Calamares job: a thin GUI front-end over janus-install.
import subprocess

import libcalamares


def pretty_name():
    return "Installing JanusOS"


def _target_device():
    gs = libcalamares.globalstorage
    parts = gs.value("partitions") or []
    for p in parts:
        dev = (p or {}).get("device")
        if dev:
            return dev
    return None


def run():
    device = _target_device()
    if not device:
        return (
            "No target disk selected",
            "Choose a disk in the partitioning step so JanusOS can be installed.",
        )
    libcalamares.utils.debug(f"janusinstall: installing to {device}")
    proc = subprocess.run(
        ["/usr/local/bin/janus-install", "--target", device, "--yes"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ("Install failed", (proc.stderr or proc.stdout)[-500:])
    return None
