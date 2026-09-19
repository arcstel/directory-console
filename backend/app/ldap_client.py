"""Thin LDAP(S) layer over a Samba AD DC, using ldap3.

Everything speaks standard LDAP to the directory. Privileged operations
(password set) require an encrypted channel, which is why the default URI is
ldaps:// and the connection is reused for read-modify sequences.
"""
from __future__ import annotations

import re
import ssl
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from ldap3 import ALL, MODIFY_ADD, MODIFY_DELETE, MODIFY_REPLACE, SIMPLE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException

from .config import settings

PAGED = "1.2.840.113556.1.4.319"
EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)

USER_ATTRS = [
    "cn", "sAMAccountName", "userPrincipalName", "givenName", "sn", "displayName",
    "mail", "title", "department", "description", "userAccountControl", "pwdLastSet",
    "lastLogonTimestamp", "whenCreated", "whenChanged", "memberOf", "distinguishedName",
    "badPwdCount", "lockoutTime", "accountExpires", "telephoneNumber", "manager",
    "company", "employeeID", "objectClass",
]
GROUP_ATTRS = [
    "cn", "sAMAccountName", "description", "groupType", "member", "distinguishedName",
    "whenCreated", "managedBy", "objectClass",
]
OU_ATTRS = ["ou", "description", "distinguishedName", "whenCreated", "objectClass"]
COMPUTER_ATTRS = [
    "cn", "dNSHostName", "operatingSystem", "operatingSystemVersion", "lastLogonTimestamp",
    "userAccountControl", "distinguishedName", "whenCreated", "objectClass",
]

ADMIN_GROUPS = {
    "Domain Admins", "Enterprise Admins", "Administrators", "Schema Admins",
    "Tier0-Admins", "Account Operators", "Backup Operators", "Group Policy Creator Owners",
}


class DirectoryError(RuntimeError):
    pass


def encode_password(password: str) -> bytes:
    """AD/Samba expect unicodePwd as the quoted password in UTF-16LE."""
    return ('"%s"' % password).encode("utf-16-le")


def _first(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def realm_from_base(base: str) -> str:
    parts = [p.split("=", 1)[1] for p in base.split(",") if p.strip().upper().startswith("DC=")]
    return ".".join(parts)


def _safe(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("latin-1", "replace")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value


def filetime_to_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n <= 0 or n >= 9223372036854775807:
        return None
    try:
        return EPOCH + timedelta(microseconds=n / 10)
    except OverflowError:
        return None


def uac_flags(uac: Any) -> dict[str, bool]:
    try:
        n = int(uac)
    except (TypeError, ValueError):
        n = 0
    return {
        "disabled": bool(n & 0x0002),
        "enabled": not bool(n & 0x0002),
        "passwordNeverExpires": bool(n & 0x10000),
        "passwordNotRequired": bool(n & 0x0020),
        "smartcardRequired": bool(n & 0x40000),
        "normalAccount": bool(n & 0x0200),
    }


def days_since(value: Any) -> int | None:
    dt = filetime_to_dt(value)
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).days


class LdapDirectory:
    mode = "ldap"

    # ---------------------------------------------------------------- plumbing
    @contextmanager
    def connection(self) -> Iterator[Connection]:
        tls = Tls(validate=ssl.CERT_REQUIRED if settings.tls_verify else ssl.CERT_NONE)
        server = Server(
            settings.host,
            port=settings.port,
            use_ssl=settings.use_ssl,
            tls=tls,
            get_info=ALL,
            connect_timeout=settings.connect_timeout,
        )
        try:
            conn = Connection(
                server,
                user=settings.bind_user,
                password=settings.bind_pass,
                authentication=SIMPLE,
                auto_bind=True,
                receive_timeout=settings.connect_timeout,
                raise_exceptions=True,
            )
        except LDAPException as exc:
            raise DirectoryError(f"LDAP bind failed: {exc}") from exc
        try:
            yield conn
        finally:
            try:
                conn.unbind()
            except Exception:
                pass

    def _search(self, conn: Connection, ldap_filter: str, attributes: list[str]) -> list[dict]:
        results: list[dict] = []
        conn.search(settings.base_dn, ldap_filter, search_scope=SUBTREE, attributes=attributes, paged_size=500)
        while True:
            for entry in conn.response:
                if isinstance(entry, dict) and entry.get("type") == "searchResEntry":
                    results.append(entry)
            cookie = None
            try:
                cookie = conn.result["controls"][PAGED]["value"]["cookie"]
            except (KeyError, TypeError):
                cookie = None
            if not cookie:
                break
            conn.search(
                settings.base_dn, ldap_filter, search_scope=SUBTREE,
                attributes=attributes, paged_size=500, paged_cookie=cookie,
            )
        return results

    @staticmethod
    def _entry(entry: dict, attrs: list[str]) -> dict:
        raw = entry.get("attributes", {})
        out: dict[str, Any] = {}
        for a in attrs:
            v = raw.get(a)
            if v in (None, [], ""):
                continue
            out[a] = _safe(v)
        return {"dn": entry.get("dn", ""), "attributes": out}

    # ------------------------------------------------------------------ health
    def health(self) -> dict:
        with self.connection() as conn:
            conn.search(settings.base_dn, "(objectClass=domain)", search_scope="BASE", attributes=["dc", "name", "distinguishedName"])
            info = _safe(conn.response[0]["attributes"]) if conn.response else {}
        return {"ok": True, "mode": "ldap", "uri": settings.ldap_uri, "base_dn": settings.base_dn, "domain": info}

    def domain(self) -> dict:
        with self.connection() as conn:
            conn.search(settings.base_dn, "(objectClass=domain)", search_scope="BASE", attributes=["dc", "name", "distinguishedName"])
            info = _safe(conn.response[0]["attributes"]) if conn.response else {}
            users = self._search(conn, "(&(objectClass=user)(!(objectClass=computer)))", ["sAMAccountName"])
            groups = self._search(conn, "(objectClass=group)", ["sAMAccountName"])
        return {
            "base_dn": settings.base_dn,
            "uri": settings.ldap_uri,
            "netbios": (info.get("name") or [None])[0] if isinstance(info.get("name"), list) else info.get("name"),
            "user_count": len(users),
            "group_count": len(groups),
        }

    # ------------------------------------------------------------------- lists
    def list_users(self, q: str = "", page: int = 1, size: int = 50) -> dict:
        attrs = USER_ATTRS
        with self.connection() as conn:
            entries = self._search(conn, "(&(objectClass=user)(!(objectClass=computer)))", attrs)
        items = [self._user_item(self._entry(e, attrs)) for e in entries]
        return self._paginate(items, q, page, size, ("cn", "sAMAccountName", "mail", "title", "department"))

    def list_groups(self, q: str = "", page: int = 1, size: int = 50) -> dict:
        attrs = GROUP_ATTRS
        with self.connection() as conn:
            entries = self._search(conn, "(objectClass=group)", attrs)
        items = [self._group_item(self._entry(e, attrs)) for e in entries]
        return self._paginate(items, q, page, size, ("cn", "sAMAccountName", "description"))

    def list_ous(self, q: str = "", page: int = 1, size: int = 50) -> dict:
        attrs = OU_ATTRS
        with self.connection() as conn:
            entries = self._search(conn, "(objectClass=organizationalUnit)", attrs)
        items = [self._ou_item(self._entry(e, attrs)) for e in entries]
        return self._paginate(items, q, page, size, ("ou", "description"))

    def list_computers(self, q: str = "", page: int = 1, size: int = 50) -> dict:
        attrs = COMPUTER_ATTRS
        with self.connection() as conn:
            entries = self._search(conn, "(objectClass=computer)", attrs)
        items = [self._computer_item(self._entry(e, attrs)) for e in entries]
        return self._paginate(items, q, page, size, ("cn", "dNSHostName", "operatingSystem"))

    # ------------------------------------------------------------- normalizers
    def _user_item(self, obj: dict) -> dict:
        a = obj["attributes"]
        flags = uac_flags(a.get("userAccountControl"))
        return {
            "dn": obj["dn"],
            "type": "user",
            "name": a.get("displayName") or a.get("cn") or a.get("sAMAccountName"),
            "sam": a.get("sAMAccountName"),
            "upn": a.get("userPrincipalName"),
            "mail": a.get("mail"),
            "title": a.get("title"),
            "department": a.get("department"),
            "description": a.get("description"),
            "enabled": flags["enabled"],
            "passwordNeverExpires": flags["passwordNeverExpires"],
            "locked": bool(a.get("lockoutTime") and str(a.get("lockoutTime")) not in ("0", "")),
            "lastLogonDays": days_since(a.get("lastLogonTimestamp")),
            "pwdLastSetDays": days_since(a.get("pwdLastSet")),
            "memberOf": a.get("memberOf", []) if isinstance(a.get("memberOf"), list) else ([a["memberOf"]] if a.get("memberOf") else []),
            "whenCreated": a.get("whenCreated"),
            "isService": bool((a.get("sAMAccountName") or "").lower().startswith("svc-")),
        }

    def _group_item(self, obj: dict) -> dict:
        a = obj["attributes"]
        members = a.get("member", [])
        if not isinstance(members, list):
            members = [members] if members else []
        try:
            gt = int(a.get("groupType", 0))
        except (TypeError, ValueError):
            gt = 0
        return {
            "dn": obj["dn"],
            "type": "group",
            "name": a.get("cn"),
            "sam": a.get("sAMAccountName"),
            "description": a.get("description"),
            "memberCount": len(members),
            "members": members,
            "security": bool(gt & 0x80000000),
            "privileged": (a.get("cn") or "") in ADMIN_GROUPS,
            "whenCreated": a.get("whenCreated"),
        }

    def _ou_item(self, obj: dict) -> dict:
        a = obj["attributes"]
        return {"dn": obj["dn"], "type": "ou", "name": a.get("ou") or a.get("cn"), "description": a.get("description"), "whenCreated": a.get("whenCreated")}

    def _computer_item(self, obj: dict) -> dict:
        a = obj["attributes"]
        flags = uac_flags(a.get("userAccountControl"))
        return {
            "dn": obj["dn"], "type": "computer", "name": a.get("cn"),
            "dns": a.get("dNSHostName"), "os": a.get("operatingSystem"),
            "osVersion": a.get("operatingSystemVersion"),
            "enabled": flags["enabled"], "lastLogonDays": days_since(a.get("lastLogonTimestamp")),
            "whenCreated": a.get("whenCreated"),
        }

    @staticmethod
    def _paginate(items: list[dict], q: str, page: int, size: int, fields: tuple) -> dict:
        if q:
            needle = q.lower()
            items = [i for i in items if any(needle in str(i.get(f, "")).lower() for f in fields)]
        items.sort(key=lambda i: str(i.get("name") or i.get("sam") or "").lower())
        total = len(items)
        start = max(0, (page - 1) * size)
        return {"total": total, "page": page, "size": size, "items": items[start:start + size]}

    # ---------------------------------------------------------------- get one
    def get_object(self, dn: str) -> dict:
        attrs = list(dict.fromkeys(USER_ATTRS + GROUP_ATTRS + OU_ATTRS + COMPUTER_ATTRS))
        with self.connection() as conn:
            conn.search(dn, "(objectClass=*)", search_scope="BASE", attributes=attrs)
            if not conn.response:
                raise DirectoryError(f"Object not found: {dn}")
            entry = self._entry(conn.response[0], attrs)
        a = entry["attributes"]
        classes = a.get("objectClass", [])
        if isinstance(classes, str):
            classes = [classes]
        if "user" in classes:
            detail = self._user_item(entry)
        elif "group" in classes:
            detail = self._group_item(entry)
        elif "organizationalUnit" in classes:
            detail = self._ou_item(entry)
        elif "computer" in classes:
            detail = self._computer_item(entry)
        else:
            detail = {"dn": entry["dn"], "type": "object", "name": a.get("cn") or dn}
        detail["raw"] = a
        return detail

    # ------------------------------------------------------------------ writes
    def create_user(self, payload: dict) -> dict:
        given = (payload.get("givenName") or "").strip()
        surname = (payload.get("surname") or "").strip()
        sam = (payload.get("sam") or "").strip()
        if not sam:
            raise DirectoryError("sAMAccountName is required")
        ou = payload.get("ou") or f"OU=People,{settings.base_dn}"
        cn = f"{given} {surname}".strip() or sam
        dn = f"CN={cn},{ou}"
        realm = realm_from_base(settings.base_dn)
        attrs = {
            "objectClass": ["top", "person", "organizationalPerson", "user"],
            "sAMAccountName": sam,
            "userPrincipalName": f"{sam}@{realm.lower()}",
            "userAccountControl": 514,  # created disabled; enabled after password set
        }
        if given:
            attrs["givenName"] = given
        if surname:
            attrs["sn"] = surname
        attrs["displayName"] = cn
        for src, dst in (("mail", "mail"), ("title", "title"), ("department", "department"), ("description", "description"), ("phone", "telephoneNumber")):
            if payload.get(src):
                attrs[dst] = payload[src]
        with self.connection() as conn:
            if not conn.add(dn, attributes=attrs):
                raise DirectoryError(f"Create failed: {conn.result}")
            try:
                password = payload.get("password") or settings.default_user_password
                if not conn.modify(dn, {"unicodePwd": [(MODIFY_REPLACE, [encode_password(password)])]}):
                    raise DirectoryError(f"Password set failed: {conn.result}")
                if not conn.modify(dn, {"userAccountControl": [(MODIFY_REPLACE, [512])]}):
                    raise DirectoryError(f"Enable failed: {conn.result}")
            except Exception:
                # Do not leave a half-created (passwordless) account behind.
                try:
                    conn.delete(dn)
                except Exception:
                    pass
                raise
        return {"dn": dn, "sam": sam}

    def create_group(self, payload: dict) -> dict:
        name = (payload.get("name") or "").strip()
        if not name:
            raise DirectoryError("Group name is required")
        ou = payload.get("ou") or f"OU=Groups,{settings.base_dn}"
        dn = f"CN={name},{ou}"
        attrs = {"objectClass": ["top", "group"], "sAMAccountName": name, "groupType": -2147483646}
        if payload.get("description"):
            attrs["description"] = payload["description"]
        with self.connection() as conn:
            if not conn.add(dn, attributes=attrs):
                raise DirectoryError(f"Create group failed: {conn.result}")
        return {"dn": dn, "name": name}

    def create_ou(self, payload: dict) -> dict:
        name = (payload.get("name") or "").strip()
        if not name:
            raise DirectoryError("OU name is required")
        parent = payload.get("parent") or settings.base_dn
        dn = f"OU={name},{parent}"
        attrs = {"objectClass": ["top", "organizationalUnit"], "ou": name}
        if payload.get("description"):
            attrs["description"] = payload["description"]
        with self.connection() as conn:
            if not conn.add(dn, attributes=attrs):
                raise DirectoryError(f"Create OU failed: {conn.result}")
        return {"dn": dn, "name": name}

    def delete_object(self, dn: str) -> dict:
        with self.connection() as conn:
            if not conn.delete(dn):
                raise DirectoryError(f"Delete failed: {conn.result}")
        return {"deleted": dn}

    def set_password(self, dn: str, password: str) -> dict:
        if not password or len(password) < 8:
            raise DirectoryError("Password must be at least 8 characters")
        with self.connection() as conn:
            if not conn.modify(dn, {"unicodePwd": [(MODIFY_REPLACE, [encode_password(password)])]}):
                raise DirectoryError(f"Password change failed: {conn.result}")
        return {"dn": dn, "updated": "password"}

    def set_enabled(self, dn: str, enabled: bool) -> dict:
        with self.connection() as conn:
            conn.search(dn, "(objectClass=*)", search_scope="BASE", attributes=["userAccountControl"])
            if not conn.response:
                raise DirectoryError(f"Object not found: {dn}")
            current = int(conn.response[0]["attributes"].get("userAccountControl") or 512)
            target = (current & ~0x0002) if enabled else (current | 0x0002)
            if not conn.modify(dn, {"userAccountControl": [(MODIFY_REPLACE, [target])]}):
                raise DirectoryError(f"Update failed: {conn.result}")
        return {"dn": dn, "enabled": enabled}

    def group_member(self, group_dn: str, member_dn: str, add: bool) -> dict:
        op = MODIFY_ADD if add else MODIFY_DELETE
        with self.connection() as conn:
            if not conn.modify(group_dn, {"member": [(op, [member_dn])]}):
                raise DirectoryError(f"Membership update failed: {conn.result}")
        return {"group": group_dn, "member": member_dn, "action": "add" if add else "remove"}

    def move_object(self, dn: str, target_dn: str) -> dict:
        rdn = dn.split(",", 1)[0]
        with self.connection() as conn:
            if not conn.modify_dn(dn, rdn, new_superior=target_dn):
                raise DirectoryError(f"Move failed: {conn.result}")
        return {"moved": dn, "to": target_dn}

    # ------------------------------------------------------------- recycle bin
    def recycle_bin(self) -> dict:
        base = f"CN=Deleted Objects,{settings.base_dn}"
        attrs = ["cn", "distinguishedName", "whenChanged", "lastKnownParent",
                 "objectClass", "sAMAccountName", "isRecycled"]
        with self.connection() as conn:
            # LDAP_SERVER_SHOW_DELETED_OID
            conn.search(base, "(isDeleted=TRUE)", search_scope=SUBTREE, attributes=attrs,
                        controls=[("1.2.840.113556.1.4.417", True, None)])
            items = []
            for e in conn.response:
                if not isinstance(e, dict) or e.get("type") != "searchResEntry":
                    continue
                if e.get("dn", "").lower() == base.lower():
                    continue  # the Deleted Objects container itself
                a = e.get("attributes", {})
                raw_name = str(_first(a.get("cn")) or _first(a.get("sAMAccountName")) or "")
                clean_name = re.sub(r"[\x00-\x1f].*$", "", raw_name).split("DEL:")[0].strip()
                items.append({
                    "dn": e.get("dn", ""),
                    "name": clean_name or raw_name,
                    "sam": _first(a.get("sAMAccountName")),
                    "whenChanged": _first(a.get("whenChanged")),
                    "lastKnownParent": _first(a.get("lastKnownParent")),
                    "recycled": str(_first(a.get("isRecycled"))).lower() in ("true", "1"),
                })
        items.sort(key=lambda i: str(i.get("whenChanged") or ""), reverse=True)
        return {"total": len(items), "items": items}

    def restore_object(self, dn: str) -> dict:
        with self.connection() as conn:
            conn.search(dn, "(objectClass=*)", search_scope="BASE",
                        attributes=["cn", "sAMAccountName", "lastKnownParent", "objectClass", "isRecycled"],
                        controls=[("1.2.840.113556.1.4.417", True, None)])
            if not conn.response:
                raise DirectoryError("Deleted object not found")
            a = conn.response[0].get("attributes", {})
            last_parent = _first(a.get("lastKnownParent")) or settings.base_dn
            raw_name = str(_first(a.get("cn")) or _first(a.get("sAMAccountName")) or "")
            name = re.sub(r"[\x00-\x1f].*$", "", raw_name).split("DEL:")[0].strip()
            if not name:
                raise DirectoryError("Cannot determine the object's original name")
            rdn = f"CN={name}"
            new_dn = f"{rdn},{last_parent}"
            # Reanimation usually means clearing isDeleted, then moving the object
            # back to its original parent (which drops the \0ADEL RDN suffix).
            try:
                conn.modify(dn, {"isDeleted": [(MODIFY_DELETE, [])]})
            except Exception:
                pass
            try:
                moved = conn.modify_dn(dn, rdn, new_superior=last_parent)
            except Exception:
                moved = False
            if moved:
                return {"restored": dn, "to": new_dn}
            raise DirectoryError(
                "This directory does not support restoring deleted objects over LDAP "
                "(a Samba AD DC limitation; Microsoft AD with the Recycle Bin enabled does). "
                "The object remains in the recycle bin."
            )
        return {"restored": dn, "to": new_dn}

    # --------------------------------------------------------------------- ACL
    def _sid_map(self, conn: Connection) -> dict:
        mapping: dict[str, str] = {}
        conn.search(settings.base_dn, "(objectSid=*)", search_scope=SUBTREE,
                    attributes=["sAMAccountName", "cn", "objectSid"])
        for e in conn.response:
            if not isinstance(e, dict) or e.get("type") != "searchResEntry":
                continue
            raw = (e.get("raw_attributes") or {}).get("objectSid")
            if not raw:
                continue
            try:
                from .sd import _sid
                sid, _ = _sid(raw[0], 0)
            except Exception:
                continue
            name = _first(e.get("attributes", {}).get("sAMAccountName")) or _first(e.get("attributes", {}).get("cn"))
            if name:
                mapping[sid] = name
        return mapping

    def object_acl(self, dn: str) -> dict:
        from .sd import friendly_sid, parse_sd
        with self.connection() as conn:
            conn.search(dn, "(objectClass=*)", search_scope="BASE",
                        attributes=["nTSecurityDescriptor", "distinguishedName", "cn"])
            if not conn.response:
                raise DirectoryError("Object not found")
            raw = (conn.response[0].get("raw_attributes") or {}).get("nTSecurityDescriptor")
            blob = raw[0] if raw else None
            smap = self._sid_map(conn)
        resolve = lambda sid: smap.get(sid) or friendly_sid(sid)
        acl = parse_sd(blob, resolve)
        acl["dn"] = dn
        return acl

    # -------------------------------------------------------------- governance
    def governance(self) -> dict:
        users = self.list_users(size=10000)["items"]
        groups = self.list_groups(size=10000)["items"]
        findings: list[dict] = []
        fid = 0

        def add(sev, cat, obj, detail):
            nonlocal fid
            fid += 1
            findings.append({"id": f"G{fid:03d}", "severity": sev, "category": cat, "dn": obj.get("dn"), "name": obj.get("name") or obj.get("sam"), "detail": detail})

        privileged_names = set()
        for g in groups:
            if g.get("privileged"):
                privileged_names.update(g.get("members", []))

        for u in users:
            who = u.get("name") or u.get("sam")
            if not u.get("enabled"):
                add("medium", "Disabled Account", u, "Account is disabled but still present in the directory.")
            if u.get("enabled") and u.get("lastLogonDays") is not None and u["lastLogonDays"] > 90 and not u.get("isService"):
                add("high", "Dormant Account", u, f"No interactive sign-in for {u['lastLogonDays']} days while enabled.")
            if u.get("enabled") and u.get("lastLogonDays") is None and not u.get("isService"):
                add("low", "Never Logged In", u, "Account has never recorded an interactive logon.")
            if u.get("passwordNeverExpires") and not u.get("isService"):
                add("medium", "Password Never Expires", u, "Interactive account flagged password-never-expires.")
            if u.get("locked"):
                add("high", "Locked Out", u, "Account is currently locked out (possible lockout attack).")
            if u.get("isService") and u.get("passwordNeverExpires"):
                add("low", "Service Account", u, "Service account with non-expiring password — verify ownership and rotation.")
            if u.get("dn") in privileged_names:
                add("critical", "Privileged Identity", u, "Member of a privileged administrative group.")

        by_cat: dict[str, int] = {}
        for f in findings:
            by_cat[f["category"]] = by_cat.get(f["category"], 0) + 1
        sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings.sort(key=lambda f: (sev_rank.get(f["severity"], 9), f["category"]))

        return {
            "summary": {
                "users": len(users),
                "groups": len(groups),
                "enabled": sum(1 for u in users if u.get("enabled")),
                "disabled": sum(1 for u in users if not u.get("enabled")),
                "privileged": sum(1 for u in users if u.get("dn") in privileged_names),
                "findings": len(findings),
                "critical": sum(1 for f in findings if f["severity"] == "critical"),
                "high": sum(1 for f in findings if f["severity"] == "high"),
                "by_category": by_cat,
            },
            "findings": findings,
        }
