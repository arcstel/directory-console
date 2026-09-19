"""Minimal parser for a self-relative Windows security descriptor.

Enough to present an object's DACL (who is allowed/denied what) read-only.
We deliberately do not *write* security descriptors here.
"""
from __future__ import annotations

import struct
from typing import Any

ACE_TYPE = {
    0x00: "Allow",
    0x01: "Deny",
    0x05: "Allow (object)",
    0x06: "Deny (object)",
    0x09: "Allow (callback)",
    0x0A: "Deny (callback)",
    0x0B: "Allow (callback object)",
    0x0C: "Deny (callback object)",
}

ACE_FLAGS = [
    (0x01, "object-inherit"),
    (0x02, "container-inherit"),
    (0x04, "no-propagate"),
    (0x08, "inherit-only"),
    (0x10, "inherited"),
]

ACCESS_BITS = [
    (0x00000001, "Create Child / Self"),
    (0x00000002, "Delete Child"),
    (0x00000004, "List Children"),
    (0x00000008, "Self / Validated Write"),
    (0x00000010, "Read Property"),
    (0x00000020, "Write Property"),
    (0x00000040, "Delete Tree"),
    (0x00000080, "List Object"),
    (0x00000100, "Control Access (extended right)"),
    (0x00010000, "Delete"),
    (0x00020000, "Read Control"),
    (0x00040000, "Write DAC"),
    (0x00080000, "Write Owner"),
    (0x00100000, "Synchronize"),
    (0x10000000, "Generic All"),
    (0x20000000, "Generic Execute"),
    (0x40000000, "Generic Write"),
    (0x80000000, "Generic Read"),
]

# Well-known SIDs -> friendly names.
KNOWN_SIDS = {
    "S-1-0-0": "Everyone",
    "S-1-1-0": "World",
    "S-1-3-0": "Creator Owner",
    "S-1-5-18": "SYSTEM",
    "S-1-5-19": "LOCAL SERVICE",
    "S-1-5-20": "NETWORK SERVICE",
    "S-1-5-7": "ANONYMOUS LOGON",
    "S-1-5-11": "Authenticated Users",
    "S-1-5-32-544": "Administrators",
    "S-1-5-32-545": "Users",
    "S-1-5-32-546": "Guests",
    "S-1-5-32-548": "Account Operators",
    "S-1-5-32-549": "Server Operators",
    "S-1-5-32-550": "Print Operators",
    "S-1-5-32-551": "Backup Operators",
    "S-1-5-32-552": "Replicators",
    "S-1-5-32-554": "Pre-Windows 2000 Compatible Access",
    "S-1-5-32-555": "Remote Desktop Users",
    "S-1-5-32-557": "Incoming Forest Trust Builders",
    "S-1-5-32-558": "Performance Monitor Users",
    "S-1-5-32-559": "Performance Log Users",
    "S-1-5-32-560": "Windows Authorization Access Group",
    "S-1-5-32-561": "Terminal Server License Servers",
    "S-1-5-32-562": "Distributed COM Users",
    "S-1-5-9": "Enterprise Domain Controllers",
}


def _sid(data: bytes, offset: int) -> tuple[str, int]:
    if offset + 8 > len(data):
        return "S-?", offset
    revision = data[offset]
    count = data[offset + 1]
    authority = int.from_bytes(data[offset + 2:offset + 8], "big")
    subs = []
    pos = offset + 8
    for _ in range(count):
        if pos + 4 > len(data):
            break
        subs.append(struct.unpack_from("<I", data, pos)[0])
        pos += 4
    sid = f"S-{revision}-{authority}" + "".join(f"-{s}" for s in subs)
    return sid, pos


def _rights(mask: int) -> list[str]:
    out = []
    for bit, label in ACCESS_BITS:
        if mask & bit:
            out.append(label)
    return out or ["(none)"]


def parse_sd(blob: bytes, resolve=None) -> dict[str, Any]:
    """Parse a self-relative security descriptor into a readable DACL.

    `resolve` optionally maps a SID string to a display name.
    """
    if not blob or len(blob) < 20:
        return {"available": False, "aces": []}

    control = struct.unpack_from("<H", blob, 2)[0]
    off_owner, off_group, off_sacl, off_dacl = struct.unpack_from("<IIII", blob, 4)

    def owner_or_group(offset: int) -> str | None:
        if not offset:
            return None
        sid, _ = _sid(blob, offset)
        return resolve(sid) if resolve else sid

    result: dict[str, Any] = {
        "available": True,
        "owner": owner_or_group(off_owner),
        "group": owner_or_group(off_group),
        "dacl_present": bool(control & 0x0004),
        "aces": [],
    }
    if not off_dacl:
        return result

    acl_rev = blob[off_dacl]
    acl_size, ace_count = struct.unpack_from("<HH", blob, off_dacl + 2)
    pos = off_dacl + 8
    end = min(len(blob), off_dacl + acl_size)

    for _ in range(ace_count):
        if pos + 4 > end:
            break
        ace_type = blob[pos]
        ace_flags = blob[pos + 1]
        ace_size = struct.unpack_from("<H", blob, pos + 2)[0]
        if ace_size < 4 or pos + ace_size > len(blob):
            break
        body = pos + 4
        mask = struct.unpack_from("<I", blob, body)[0]
        sid_off = body + 4
        if ace_type in (0x05, 0x06, 0x0B, 0x0C):  # object ACEs carry GUID flags
            flags = struct.unpack_from("<I", blob, body + 4)[0]
            sid_off = body + 8
            if flags & 0x1:
                sid_off += 16
            if flags & 0x2:
                sid_off += 16
        sid, _ = _sid(blob, sid_off)
        result["aces"].append({
            "type": ACE_TYPE.get(ace_type, f"Type {ace_type:#x}"),
            "flags": [name for bit, name in ACE_FLAGS if ace_flags & bit],
            "mask": mask,
            "rights": _rights(mask),
            "sid": sid,
            "principal": resolve(sid) if resolve else sid,
        })
        pos += ace_size

    return result


def friendly_sid(sid: str) -> str:
    return KNOWN_SIDS.get(sid, sid)
