#!/bin/bash
set -euo pipefail

DOMAIN="${DOMAIN:-EXAMPLE}"
REALM="${REALM:-${DOMAIN}.LOCAL}"
ADMIN_PASS="${ADMIN_PASS:-Passw0rd!2026}"
DNS_FORWARDER="${DNS_FORWARDER:-1.1.1.1}"
SEED="${SEED:-true}"

SHORT="$(echo "${DOMAIN}" | tr '[:upper:]' '[:lower:]')"
FQDN="dc1.${SHORT}.local"

log() { echo "[dc] $*"; }

# Make the DC resolve its own FQDN (provisioning and Kerberos depend on it).
if ! grep -qi "${FQDN}" /etc/hosts; then
  echo "127.0.0.1   ${FQDN} dc1 localhost" >> /etc/hosts
fi

if [ ! -f /var/lib/samba/private/sam.ldb ]; then
  log "No domain found. Provisioning ${REALM} ..."
  rm -f /etc/samba/smb.conf
  if ! samba-tool domain provision \
        --use-rfc2307 \
        --domain="${DOMAIN}" \
        --realm="${REALM}" \
        --server-role=dc \
        --adminpass="${ADMIN_PASS}" \
        --dns-backend=SAMBA_INTERNAL \
        --option="dns forwarder = ${DNS_FORWARDER}" \
        --option="bind interfaces only = yes" \
        --option="interfaces = lo eth0"; then
    log "Provisioning FAILED. Wiping partial state so the next start retries cleanly."
    rm -rf /var/lib/samba/private/* /var/lib/samba/sysvol /var/lib/samba/etc 2>/dev/null || true
    rm -f /etc/samba/smb.conf
    exit 1
  fi
  cp -f /var/lib/samba/private/krb5.conf /etc/krb5.conf
  log "Provisioning complete."
else
  log "Existing domain found; skipping provisioning."
fi

log "Starting Samba AD DC..."
samba --foreground --no-process-group &
SAMBA_PID=$!

# Wait for LDAP to come up.
for i in $(seq 1 60); do
  if timeout 2 bash -c 'exec 3<>/dev/tcp/127.0.0.1/389' 2>/dev/null; then
    log "LDAP is up after ${i} attempt(s)."
    break
  fi
  sleep 2
done

if [ "${SEED}" = "true" ] && [ ! -f /var/lib/samba/.seeded ]; then
  log "Seeding sample directory content..."
  /usr/local/bin/seed.sh "${REALM}" || log "Seed encountered errors (continuing)."
  touch /var/lib/samba/.seeded
fi

wait "${SAMBA_PID}"
