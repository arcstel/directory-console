import os
from urllib.parse import urlparse


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    """Runtime configuration, read from the environment."""

    ldap_uri: str = os.getenv("LDAP_URI", "ldaps://dc:636")
    base_dn: str = os.getenv("LDAP_BASE_DN", "DC=example,DC=local")
    bind_user: str = os.getenv("LDAP_BIND_USER", "Administrator@example.local")
    bind_pass: str = os.getenv("LDAP_BIND_PASS", "Passw0rd!2026")
    tls_verify: bool = _bool("LDAP_TLS_VERIFY", False)
    default_user_password: str = os.getenv("DEFAULT_USER_PASSWORD", "ChangeMe!2026")
    mock: bool = _bool("JANUS_MOCK", False)
    connect_timeout: int = int(os.getenv("LDAP_CONNECT_TIMEOUT", "8"))
    app_name: str = "Janus Directory Console"

    # Appliance mode: enables first-run provisioning from the UI and shell.
    appliance: bool = _bool("JANUS_APPLIANCE", False)
    samba_private: str = os.getenv("SAMBA_PRIVATE", "/var/lib/samba/private")
    conf_path: str = os.getenv("JANUS_CONF", "/etc/janus/janus.conf")
    env_path: str = os.getenv("JANUS_ENV", "/etc/janus/janus.env")
    seed_script: str = os.getenv("JANUS_SEED_SCRIPT", "/usr/local/bin/janus-seed")
    console_unit: str = os.getenv("JANUS_CONSOLE_UNIT", "janus-console.service")
    samba_unit: str = os.getenv("JANUS_SAMBA_UNIT", "samba-ad-dc.service")

    @property
    def scheme(self) -> str:
        return urlparse(self.ldap_uri).scheme or "ldap"

    @property
    def host(self) -> str:
        return urlparse(self.ldap_uri).hostname or "dc"

    @property
    def port(self) -> int:
        parsed = urlparse(self.ldap_uri)
        if parsed.port:
            return parsed.port
        return 636 if self.scheme == "ldaps" else 389

    @property
    def use_ssl(self) -> bool:
        return self.scheme == "ldaps"


settings = Settings()
