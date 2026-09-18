"""Boot-time auto-provisioning entry point for the appliance.

Invoked by janus-provision.service. Reads /etc/janus/janus.conf and, when
AUTO_PROVISION=true and no domain exists yet, provisions the Samba AD DC.
"""
from __future__ import annotations

import os
import sys

from .config import settings


def parse_conf(path: str) -> dict:
    values: dict[str, str] = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def main() -> int:
    # Running as the provision service always implies appliance mode.
    settings.appliance = True

    from .appliance import is_provisioned, provision

    if is_provisioned():
        print("[janus-provision] domain already provisioned; nothing to do")
        return 0

    conf = parse_conf(settings.conf_path)
    if conf.get("AUTO_PROVISION", "false").lower() != "true":
        print("[janus-provision] AUTO_PROVISION disabled; awaiting the setup wizard")
        return 0

    try:
        result = provision(
            conf.get("DOMAIN", "EXAMPLE"),
            conf.get("REALM", "EXAMPLE.LOCAL"),
            conf.get("ADMIN_PASS", "Passw0rd!2026"),
            conf.get("SEED", "true").lower() == "true",
            conf.get("DNS_FORWARDER", "1.1.1.1"),
        )
    except Exception as exc:  # surfaced in the journal
        print(f"[janus-provision] ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"[janus-provision] provisioned {result['domain']} ({result['realm']}) base={result['base_dn']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
