"""First-run provisioning for the bootable appliance (Tier 2).

In appliance mode the console runs as root on the device and can create a Samba
AD DC in place: `samba-tool domain provision`, drop a Kerberos config, write the
appliance config, optionally seed sample content, and start the DC. The same code
backs both the boot-time auto-provision service and the web setup wizard.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess

from .config import settings

log = logging.getLogger("dcc.appliance")


def realm_to_base_dn(realm: str) -> str:
    parts = [p for p in re.split(r"[.\-]", realm.strip()) if p]
    return ",".join("DC=" + p.lower() for p in parts)


def is_provisioned() -> bool:
    private = settings.samba_private
    return os.path.exists(os.path.join(private, "sam.ldb")) or os.path.isdir(os.path.join(private, "sam.ldb.d"))


def status() -> dict:
    return {
        "appliance": settings.appliance,
        "provisioned": is_provisioned(),
        "samba": shutil.which("samba-tool") is not None,
        "domain": os.getenv("DCC_DOMAIN", "EXAMPLE"),
        "realm": os.getenv("DCC_REALM", "EXAMPLE.LOCAL"),
    }


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    log.info("run: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True)


def _normalize(domain: str, realm: str) -> tuple[str, str]:
    dom = re.sub(r"[^A-Za-z0-9]", "", (domain or "").strip()).upper() or "EXAMPLE"
    rea = (realm or "").strip().upper()
    if not rea:
        rea = dom + ".LOCAL"
    if "." not in rea:
        rea = rea + ".LOCAL"
    return dom, rea


def _write_config(domain: str, realm: str, admin_pass: str, seed: bool, forwarder: str) -> None:
    os.makedirs(os.path.dirname(settings.conf_path), exist_ok=True)
    with open(settings.conf_path, "w", encoding="utf-8") as fh:
        fh.write(
            "# Directory Control Center appliance configuration\n"
            f"DOMAIN={domain}\n"
            f"REALM={realm}\n"
            f"ADMIN_PASS={admin_pass}\n"
            f"DNS_FORWARDER={forwarder}\n"
            f"SEED={'true' if seed else 'false'}\n"
            "AUTO_PROVISION=true\n"
        )
    base_dn = realm_to_base_dn(realm)
    with open(settings.env_path, "w", encoding="utf-8") as fh:
        fh.write(
            "DCC_APPLIANCE=1\n"
            "LDAP_URI=ldaps://127.0.0.1:636\n"
            f"LDAP_BASE_DN={base_dn}\n"
            f"LDAP_BIND_USER=Administrator@{realm.lower()}\n"
            f"LDAP_BIND_PASS={admin_pass}\n"
            "LDAP_TLS_VERIFY=false\n"
        )
    os.chmod(settings.env_path, 0o600)


def _apply_inprocess(admin_pass: str, realm: str) -> None:
    """Point the running console at the freshly created domain (no restart)."""
    base_dn = realm_to_base_dn(realm)
    settings.appliance = True
    settings.ldap_uri = "ldaps://127.0.0.1:636"
    settings.base_dn = base_dn
    settings.bind_user = f"Administrator@{realm.lower()}"
    settings.bind_pass = admin_pass
    settings.tls_verify = False
    from . import directory as _directory
    _directory._directory = None  # rebuild the LDAP backend on next request


def _start_samba() -> str:
    try:
        res = subprocess.run(["systemctl", "start", settings.samba_unit], capture_output=True, text=True)
        if res.returncode != 0:
            return res.stderr.strip() or "systemctl start failed"
    except FileNotFoundError:
        return "systemctl not available"
    return ""


def provision(domain: str, realm: str, admin_pass: str, seed: bool = True, dns_forwarder: str = "1.1.1.1") -> dict:
    if not settings.appliance:
        raise RuntimeError("First-run provisioning is only available in appliance mode")
    if is_provisioned():
        raise RuntimeError("This appliance is already provisioned.")
    if not admin_pass or len(admin_pass) < 8:
        raise RuntimeError("The administrator password must be at least 8 characters.")
    if not shutil.which("samba-tool"):
        raise RuntimeError("samba-tool was not found on this appliance.")

    domain, realm = _normalize(domain, realm)

    if os.path.exists("/etc/samba/smb.conf"):
        os.remove("/etc/samba/smb.conf")
    os.makedirs(settings.samba_private, exist_ok=True)

    res = _run([
        "samba-tool", "domain", "provision",
        "--use-rfc2307",
        f"--domain={domain}",
        f"--realm={realm}",
        "--server-role=dc",
        f"--adminpass={admin_pass}",
        "--dns-backend=SAMBA_INTERNAL",
        f"--option=dns forwarder = {dns_forwarder}",
    ])
    if res.returncode != 0:
        raise RuntimeError("Provisioning failed: " + (res.stderr or res.stdout or "unknown error").strip()[-400:])

    try:
        shutil.copy("/var/lib/samba/private/krb5.conf", "/etc/krb5.conf")
    except Exception:
        log.warning("Could not install /etc/krb5.conf")

    _write_config(domain, realm, admin_pass, seed, dns_forwarder)
    _apply_inprocess(admin_pass, realm)

    seeded = False
    if seed and os.path.exists(settings.seed_script):
        seed_res = _run([settings.seed_script, realm])
        seeded = seed_res.returncode == 0
        if not seeded:
            log.warning("Seed script failed: %s", (seed_res.stderr or "")[-300:])

    start_error = _start_samba()

    return {
        "provisioned": True,
        "domain": domain,
        "realm": realm,
        "base_dn": realm_to_base_dn(realm),
        "seeded": seeded,
        "samba_start": "ok" if not start_error else start_error,
    }
