import csv
import io

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from ..appliance import provision as appliance_provision
from ..appliance import status as appliance_status
from ..directory import get_directory

router = APIRouter(prefix="/api")


def _dir():
    return get_directory()


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # DirectoryError and friends -> clean 400/503
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ------------------------------------------------------------------- schemas
class UserCreate(BaseModel):
    sam: str = Field(min_length=1)
    givenName: str = ""
    surname: str = ""
    password: str | None = None
    mail: str = ""
    title: str = ""
    department: str = ""
    description: str = ""
    phone: str = ""
    ou: str | None = None


class GroupCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    ou: str | None = None


class OUCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    parent: str | None = None


class PasswordReset(BaseModel):
    dn: str
    password: str


class EnableBody(BaseModel):
    dn: str
    enabled: bool


class MemberBody(BaseModel):
    group_dn: str
    member_dn: str
    add: bool = True


class MoveBody(BaseModel):
    dn: str
    target_dn: str


class DeleteBody(BaseModel):
    dn: str


class CsvImport(BaseModel):
    csv: str


class RestoreBody(BaseModel):
    dn: str


class ProvisionBody(BaseModel):
    domain: str = "EXAMPLE"
    realm: str = "EXAMPLE.LOCAL"
    admin_pass: str
    seed: bool = True
    dns_forwarder: str = "1.1.1.1"


# -------------------------------------------------------------------- reads
@router.get("/health")
def health():
    try:
        return _dir().health()
    except Exception as exc:
        return {"ok": False, "mode": type(_dir()).mode, "error": str(exc)}


@router.get("/domain")
def domain():
    return _call(_dir().domain)


@router.get("/users")
def users(q: str = "", page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=1000)):
    return _call(_dir().list_users, q=q, page=page, size=size)


@router.get("/groups")
def groups(q: str = "", page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=1000)):
    return _call(_dir().list_groups, q=q, page=page, size=size)


@router.get("/ous")
def ous(q: str = "", page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=1000)):
    return _call(_dir().list_ous, q=q, page=page, size=size)


@router.get("/computers")
def computers(q: str = "", page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=1000)):
    return _call(_dir().list_computers, q=q, page=page, size=size)


@router.get("/object")
def object_detail(dn: str):
    return _call(_dir().get_object, dn)


@router.get("/governance")
def governance():
    return _call(_dir().governance)


# -------------------------------------------------------- import / export
def _csv_response(rows: list[dict], fields: list[str], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: (";".join(v) if isinstance(v, list) else v) for k, v in r.items()})
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/users")
def export_users():
    items = _call(_dir().list_users, q="", page=1, size=100000)["items"]
    fields = ["sam", "name", "mail", "title", "department", "enabled", "passwordNeverExpires", "lastLogonDays", "memberOf"]
    return _csv_response(items, fields, "janus-users.csv")


@router.get("/export/groups")
def export_groups():
    items = _call(_dir().list_groups, q="", page=1, size=100000)["items"]
    fields = ["sam", "name", "description", "memberCount", "privileged"]
    return _csv_response(items, fields, "janus-groups.csv")


@router.post("/import/users")
def import_users(body: CsvImport):
    reader = csv.DictReader(io.StringIO(body.csv))
    directory = _dir()
    results = []
    created = 0
    for row in reader:
        sam = (row.get("sam") or row.get("sAMAccountName") or "").strip()
        if not sam:
            results.append({"sam": "", "ok": False, "error": "missing sam"})
            continue
        payload = {
            "sam": sam,
            "givenName": row.get("givenName", ""),
            "surname": row.get("surname", ""),
            "password": row.get("password") or None,
            "mail": row.get("mail", ""),
            "title": row.get("title", ""),
            "department": row.get("department", ""),
            "ou": row.get("ou") or None,
        }
        try:
            directory.create_user(payload)
            created += 1
            results.append({"sam": sam, "ok": True})
        except Exception as exc:
            results.append({"sam": sam, "ok": False, "error": str(exc)})
    return {"created": created, "total": len(results), "results": results}


# ---------------------------------------------------------------- recycle bin
@router.get("/recycle")
def recycle():
    return _call(_dir().recycle_bin)


@router.post("/actions/restore")
def restore(body: RestoreBody):
    return _call(_dir().restore_object, body.dn)


@router.get("/object/acl")
def object_acl(dn: str):
    return _call(_dir().object_acl, dn)


# ----------------------------------------------------- appliance provisioning
@router.get("/setup/status")
def setup_status():
    return appliance_status()


@router.post("/setup/provision")
def setup_provision(body: ProvisionBody):
    return _call(appliance_provision, body.domain, body.realm, body.admin_pass, body.seed, body.dns_forwarder)


# ------------------------------------------------------------------- writes
@router.post("/users", status_code=201)
def create_user(body: UserCreate):
    return _call(_dir().create_user, body.model_dump())


@router.post("/groups", status_code=201)
def create_group(body: GroupCreate):
    return _call(_dir().create_group, body.model_dump())


@router.post("/ous", status_code=201)
def create_ou(body: OUCreate):
    return _call(_dir().create_ou, body.model_dump())


@router.post("/actions/password")
def set_password(body: PasswordReset):
    return _call(_dir().set_password, body.dn, body.password)


@router.post("/actions/enable")
def set_enabled(body: EnableBody):
    return _call(_dir().set_enabled, body.dn, body.enabled)


@router.post("/actions/member")
def group_member(body: MemberBody):
    return _call(_dir().group_member, body.group_dn, body.member_dn, body.add)


@router.post("/actions/move")
def move(body: MoveBody):
    return _call(_dir().move_object, body.dn, body.target_dn)


@router.post("/actions/delete")
def delete(body: DeleteBody):
    return _call(_dir().delete_object, body.dn)
