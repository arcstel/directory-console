"""In-memory directory used when JANUS_MOCK=1.

Lets the console run and be demoed without a live Samba AD DC. Mirrors the
LdapDirectory interface so the API and UI behave identically.
"""
from __future__ import annotations

from .config import settings
from .ldap_client import realm_from_base


def _u(sam, name, title, dept, enabled=True, never=False, days=1, is_svc=False, groups=None):
    dn = f"CN={name},OU=People,{settings.base_dn}"
    return {
        "dn": dn, "type": "user", "name": name, "sam": sam,
        "upn": f"{sam}@{realm_from_base(settings.base_dn).lower()}",
        "mail": f"{sam}@{realm_from_base(settings.base_dn).lower()}",
        "title": title, "department": dept, "description": dept,
        "enabled": enabled, "passwordNeverExpires": never, "locked": False,
        "lastLogonDays": days, "pwdLastSetDays": 30,
        "memberOf": groups or [], "whenCreated": "2024-01-01T00:00:00+00:00",
        "isService": is_svc,
    }


class MockDirectory:
    mode = "mock"

    def __init__(self) -> None:
        self.users = [
            _u("jdoe", "John Doe", "Directory Services Admin", "IT", days=2, groups=["Tier0-Admins"]),
            _u("mchen", "Maya Chen", "Systems Engineer", "IT", days=1, groups=["Tier0-Admins"]),
            _u("rpatel", "Ravi Patel", "Cloud Engineer", "IT", days=200),
            _u("asmith", "Amy Smith", "Payroll Specialist", "Finance", days=5, groups=["Finance-Team"]),
            _u("dkhan", "Dara Khan", "Accounts Payable Clerk", "Finance", days=180, groups=["Finance-Team"]),
            _u("lnguyen", "Linh Nguyen", "Registered Nurse", "Nursing", days=3, groups=["Nursing"]),
            _u("obrown", "Omar Brown", "Physician", "Nursing", days=1, groups=["Nursing"]),
            _u("tsmith", "Tom Smith", "Help Desk Technician", "IT Support", days=2, groups=["HelpDesk"]),
            _u("kdavis", "Kim Davis", "Help Desk Technician", "IT Support", enabled=False, days=400, groups=["HelpDesk"]),
            _u("cjones", "Chris Jones", "Platform Consultant", "External", days=240, groups=["Contractors"]),
            _u("mlee", "Morgan Lee", "Security Consultant", "External", enabled=False, days=300, groups=["Contractors"]),
            _u("svc-backup", "Backup Service", "Service Account", "Service", never=True, is_svc=True),
            _u("svc-monitor", "Monitoring Service", "Service Account", "Service", never=True, is_svc=True),
            _u("svc-web", "Web App Pool", "Service Account", "Service", never=True, is_svc=True),
        ]
        self.groups = [
            self._g("Tier0-Admins", ["jdoe", "mchen"], "Privileged directory administration", True),
            self._g("HelpDesk", ["tsmith", "kdavis"], "Tier 1/2 support", False),
            self._g("Finance-Team", ["asmith", "dkhan"], "Finance and payroll", False),
            self._g("Nursing", ["lnguyen", "obrown"], "Clinical staff", False),
            self._g("Contractors", ["cjones", "mlee"], "External contractors", False),
        ]
        self.ous = [
            {"dn": f"OU=People,{settings.base_dn}", "type": "ou", "name": "People", "description": "Staff accounts", "whenCreated": "2024-01-01T00:00:00+00:00"},
            {"dn": f"OU=Groups,{settings.base_dn}", "type": "ou", "name": "Groups", "description": "Security groups", "whenCreated": "2024-01-01T00:00:00+00:00"},
            {"dn": f"OU=ServiceAccounts,{settings.base_dn}", "type": "ou", "name": "ServiceAccounts", "description": "Non-human identities", "whenCreated": "2024-01-01T00:00:00+00:00"},
            {"dn": f"OU=Contractors,{settings.base_dn}", "type": "ou", "name": "Contractors", "description": "External identities", "whenCreated": "2024-01-01T00:00:00+00:00"},
            {"dn": f"OU=Disabled,{settings.base_dn}", "type": "ou", "name": "Disabled", "description": "Offboarded accounts", "whenCreated": "2024-01-01T00:00:00+00:00"},
        ]
        self.computers = [
            {"dn": f"CN=DC1,OU=Domain Controllers,{settings.base_dn}", "type": "computer", "name": "DC1", "dns": "dc1.example.local", "os": "Samba", "osVersion": "4.x", "enabled": True, "lastLogonDays": 0, "whenCreated": "2024-01-01T00:00:00+00:00"},
            {"dn": f"CN=WKS-0142,OU=Workstations,{settings.base_dn}", "type": "computer", "name": "WKS-0142", "dns": "wks-0142.example.local", "os": "Windows 11", "osVersion": "10.0.22631", "enabled": True, "lastLogonDays": 3, "whenCreated": "2024-03-01T00:00:00+00:00"},
        ]

    def _g(self, name, sam_list, desc, priv):
        members = [next(u["dn"] for u in self.users if u["sam"] == s) for s in sam_list]
        return {"dn": f"CN={name},OU=Groups,{settings.base_dn}", "type": "group", "name": name, "sam": name,
                "description": desc, "memberCount": len(members), "members": members, "security": True,
                "privileged": priv, "whenCreated": "2024-01-01T00:00:00+00:00"}

    # ------------------------------------------------------------------ health
    def health(self) -> dict:
        return {"ok": True, "mode": "mock", "uri": "in-memory", "base_dn": settings.base_dn}

    def domain(self) -> dict:
        return {"base_dn": settings.base_dn, "uri": "in-memory", "netbios": "EXAMPLE", "user_count": len(self.users), "group_count": len(self.groups)}

    # ------------------------------------------------------------------- lists
    def _paginate(self, items, q, page, size, fields):
        if q:
            needle = q.lower()
            items = [i for i in items if any(needle in str(i.get(f, "")).lower() for f in fields)]
        items = sorted(items, key=lambda i: str(i.get("name") or i.get("sam") or "").lower())
        total = len(items)
        start = max(0, (page - 1) * size)
        return {"total": total, "page": page, "size": size, "items": items[start:start + size]}

    def list_users(self, q="", page=1, size=50):
        return self._paginate(self.users, q, page, size, ("name", "sam", "mail", "title", "department"))

    def list_groups(self, q="", page=1, size=50):
        return self._paginate(self.groups, q, page, size, ("name", "sam", "description"))

    def list_ous(self, q="", page=1, size=50):
        return self._paginate(self.ous, q, page, size, ("name", "description"))

    def list_computers(self, q="", page=1, size=50):
        return self._paginate(self.computers, q, page, size, ("name", "dns", "os"))

    def get_object(self, dn):
        for coll in (self.users, self.groups, self.ous, self.computers):
            for obj in coll:
                if obj["dn"].lower() == dn.lower():
                    out = dict(obj)
                    out["raw"] = {k: v for k, v in obj.items()}
                    return out
        return {"dn": dn, "type": "object", "name": dn, "raw": {}}

    # ------------------------------------------------------------------ writes
    def create_user(self, payload):
        sam = (payload.get("sam") or "").strip()
        given = (payload.get("givenName") or "").strip()
        surname = (payload.get("surname") or "").strip()
        name = f"{given} {surname}".strip() or sam
        ou = payload.get("ou") or f"OU=People,{settings.base_dn}"
        u = _u(sam, name, payload.get("title") or "", payload.get("department") or "", days=None)
        u.update({"mail": payload.get("mail") or u["mail"], "dn": f"CN={name},{ou}", "memberOf": []})
        self.users.append(u)
        return {"dn": u["dn"], "sam": sam}

    def create_group(self, payload):
        name = (payload.get("name") or "").strip()
        ou = payload.get("ou") or f"OU=Groups,{settings.base_dn}"
        self.groups.append({"dn": f"CN={name},{ou}", "type": "group", "name": name, "sam": name,
                            "description": payload.get("description") or "", "memberCount": 0,
                            "members": [], "security": True, "privileged": False, "whenCreated": None})
        return {"dn": f"CN={name},{ou}", "name": name}

    def create_ou(self, payload):
        name = (payload.get("name") or "").strip()
        parent = payload.get("parent") or settings.base_dn
        self.ous.append({"dn": f"OU={name},{parent}", "type": "ou", "name": name,
                         "description": payload.get("description") or "", "whenCreated": None})
        return {"dn": f"OU={name},{parent}", "name": name}

    def delete_object(self, dn):
        for coll in (self.users, self.groups, self.ous, self.computers):
            coll[:] = [o for o in coll if o["dn"].lower() != dn.lower()]
        return {"deleted": dn}

    def set_password(self, dn, password):
        return {"dn": dn, "updated": "password"}

    def set_enabled(self, dn, enabled):
        for u in self.users:
            if u["dn"].lower() == dn.lower():
                u["enabled"] = enabled
        return {"dn": dn, "enabled": enabled}

    def group_member(self, group_dn, member_dn, add):
        for g in self.groups:
            if g["dn"].lower() == group_dn.lower():
                if add and member_dn not in g["members"]:
                    g["members"].append(member_dn)
                if not add and member_dn in g["members"]:
                    g["members"].remove(member_dn)
                g["memberCount"] = len(g["members"])
        return {"group": group_dn, "member": member_dn, "action": "add" if add else "remove"}

    def move_object(self, dn, target_dn):
        rdn = dn.split(",", 1)[0]
        for coll in (self.users, self.groups, self.ous, self.computers):
            for obj in coll:
                if obj["dn"].lower() == dn.lower():
                    obj["dn"] = f"{rdn},{target_dn}"
        return {"moved": dn, "to": target_dn, "new_dn": f"{rdn},{target_dn}"}

    def recycle_bin(self):
        return {
            "total": 2,
            "items": [
                {
                    "dn": f"CN=Former Employee\\0ADEL:11111111-2222-3333-4444-555555555555,CN=Deleted Objects,{settings.base_dn}",
                    "name": "Former Employee", "sam": "femployee",
                    "whenChanged": "2026-08-01T10:00:00+00:00",
                    "lastKnownParent": f"OU=People,{settings.base_dn}", "recycled": False,
                },
                {
                    "dn": f"CN=Old Contractor\\0ADEL:66666666-7777-8888-9999-000000000000,CN=Deleted Objects,{settings.base_dn}",
                    "name": "Old Contractor", "sam": "ocontractor",
                    "whenChanged": "2026-07-15T09:30:00+00:00",
                    "lastKnownParent": f"OU=Contractors,{settings.base_dn}", "recycled": True,
                },
            ],
        }

    def restore_object(self, dn):
        return {"restored": dn, "to": f"CN=Restored,OU=People,{settings.base_dn}"}

    def object_acl(self, dn):
        return {
            "available": True,
            "dn": dn,
            "owner": "Domain Admins",
            "group": "Domain Users",
            "dacl_present": True,
            "aces": [
                {"type": "Allow", "flags": ["inherited"], "mask": 0x000f01ff,
                 "rights": ["Create Child / Self", "Delete Child", "List Children", "Self / Validated Write",
                            "Read Property", "Write Property", "Delete", "Read Control"],
                 "sid": "S-1-5-21-0000000000", "principal": "Authenticated Users"},
                {"type": "Allow", "flags": [], "mask": 0x000f01ff,
                 "rights": ["Create Child / Self", "Delete Child", "List Children", "Read Property"],
                 "sid": "S-1-5-21-1111111111", "principal": "Tier0-Admins"},
            ],
        }

    def governance(self):
        return _governance(self.list_users(size=10000)["items"], self.list_groups(size=10000)["items"])


def _governance(users, groups):
    findings = []
    fid = 0
    privileged = set()
    for g in groups:
        if g.get("privileged"):
            privileged.update(g.get("members", []))

    def add(sev, cat, obj, detail):
        nonlocal fid
        fid += 1
        findings.append({"id": f"G{fid:03d}", "severity": sev, "category": cat, "dn": obj.get("dn"),
                         "name": obj.get("name") or obj.get("sam"), "detail": detail})

    for u in users:
        if not u.get("enabled"):
            add("medium", "Disabled Account", u, "Account is disabled but still present in the directory.")
        if u.get("enabled") and u.get("lastLogonDays") is not None and u["lastLogonDays"] > 90 and not u.get("isService"):
            add("high", "Dormant Account", u, f"No interactive sign-in for {u['lastLogonDays']} days while enabled.")
        if u.get("passwordNeverExpires") and not u.get("isService"):
            add("medium", "Password Never Expires", u, "Interactive account flagged password-never-expires.")
        if u.get("isService") and u.get("passwordNeverExpires"):
            add("low", "Service Account", u, "Service account with non-expiring password — verify ownership and rotation.")
        if u.get("dn") in privileged:
            add("critical", "Privileged Identity", u, "Member of a privileged administrative group.")

    by_cat = {}
    for f in findings:
        by_cat[f["category"]] = by_cat.get(f["category"], 0) + 1
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: (rank.get(f["severity"], 9), f["category"]))
    return {
        "summary": {
            "users": len(users), "groups": len(groups),
            "enabled": sum(1 for u in users if u.get("enabled")),
            "disabled": sum(1 for u in users if not u.get("enabled")),
            "privileged": sum(1 for u in users if u.get("dn") in privileged),
            "findings": len(findings),
            "critical": sum(1 for f in findings if f["severity"] == "critical"),
            "high": sum(1 for f in findings if f["severity"] == "high"),
            "by_category": by_cat,
        },
        "findings": findings,
    }
