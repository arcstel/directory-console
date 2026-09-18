# Directory Control Center (DCC)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/arcstel/directory-console)

> **Try it with zero setup**
> - **Simulated demo (instant):** <https://arcstel.github.io/dcc/> — the real UI running fully
>   client-side against an in-memory directory of fake users. Actions work; state resets on refresh.
> - **Real lab (Codespaces):** click *Open in GitHub Codespaces* above. It builds the actual
>   Samba AD DC + console and forwards port 8000. First boot takes a few minutes.

A browser-based Active Directory management console for Linux — an ADAC-style
experience for the open stack. It talks **LDAP/LDAPS** to a **self-contained
Samba AD DC** (no Microsoft licensing) and layers identity-governance reporting
on top: privileged identities, dormant and disabled accounts, non-expiring
passwords, and stale access.

> Working title. Rename freely. Not affiliated with Microsoft; "ADAC" is their
> product and we do not use their binaries.

This is **Tier 1** of the roadmap: the console as a Docker app. Tier 2 packages
it as a bootable Arch-based appliance (see Roadmap).

## What works today

- Domain dashboard: user/group/enabled/disabled/privileged/findings counters.
- **Users** — search, paginate, inspect; create; reset password; enable/disable;
  add to group; move OU; delete.
- **Groups** — list, membership counts, privileged-group flagging, add members.
- **Organizational Units** — list and create.
- **Computers** — inventory.
- **Governance** — risk findings with severity, click-through to the object.
- All writes go over LDAPS; passwords use the AD `unicodePwd` convention.

## Architecture

```
┌────────────────┐   LDAPS :636   ┌──────────────────────┐
│  console       │ ─────────────► │  Samba AD DC         │
│  FastAPI + JS  │   LDAP :389    │  (internal DNS)      │
│  :8000 → host  │                │  dc1.example.local   │
└────────────────┘                └──────────────────────┘
        docker network: dccnet (only 8000 is published)
```

| Path | Purpose |
| --- | --- |
| `docker-compose.yml` | Two services: `dc` (Samba AD DC, auto-provisioned) and `console`. |
| `samba/` | DC image: `entrypoint.sh` provisions on first boot, `seed.sh` creates sample OUs/groups/users. |
| `backend/app/ldap_client.py` | LDAP(S) layer: search, CRUD, password set, governance analysis. |
| `backend/app/mock.py` | In-memory directory for `DCC_MOCK=1` demos with no DC. |
| `backend/app/routers/api.py` | REST API. |
| `backend/app/static/` | The console SPA (no build step). |

## Quick start

```bash
cp .env.example .env          # optional; defaults work
make up                       # build + start DC and console
# open http://localhost:8000
```

First boot provisions `EXAMPLE.LOCAL` and seeds sample content (~40s).

```bash
make logs        # follow
make ps          # status
make down        # stop
make reset       # wipe volumes (destroys the domain) and restart
make mock        # run the console alone against built-in sample data
```

Default admin bind: `Administrator@example.local` / `Passw0rd!2026`
(override in `.env`). **Change these before exposing the console anywhere.**

## Notes / gotchas

- Provisioning sets `security.*` xattrs on SYSVOL, so the `dc` container needs
  `cap_add: SYS_ADMIN` (already configured) and is left `apparmor:unconfined`.
- Passwords are set as `unicodePwd` with the required quoting + UTF-16LE.
- TLS verification is off by default because the DC ships a self-signed cert.
  Set `LDAP_TLS_VERIFY=true` and trust the CA for anything real.

## Roadmap

- [x] **Tier 1** — web console over a self-contained Samba AD DC (this repo).
- [ ] **Tier 1.1** — delegation/ACL editor, group nesting view, recycle bin,
      fine-grained password policies, CSV import/export, scheduled reports.
- [ ] **Tier 2** — `archiso` live appliance bundling `dc` + console + tooling,
      boot to a working console with an auto-provision wizard.
- [ ] **Tier 3** — installable branded distro (Calamares), update channel, docs.

## Safety

All sample data is fabricated. The console performs real LDAP writes — run it
against a lab domain, never production, until auditing and RBAC are added.
