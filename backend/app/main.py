import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .directory import get_directory
from .routers import api

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dcc")

app = FastAPI(title=settings.app_name, version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(api.router)

static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.on_event("startup")
def startup() -> None:
    directory = get_directory()
    log.info("Directory Control Center starting in %s mode (base=%s)", directory.mode, settings.base_dn)
    if directory.mode == "ldap":
        try:
            directory.health()
            log.info("LDAP connectivity OK: %s", settings.ldap_uri)
        except Exception as exc:  # pragma: no cover - startup diagnostics only
            log.warning("LDAP not reachable yet: %s", exc)
