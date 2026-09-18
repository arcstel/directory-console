from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

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
