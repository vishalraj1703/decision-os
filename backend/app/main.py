"""Decision OS API. Bound to localhost; the browser reaches it only through the Next.js server,
which authenticates the user (NextAuth) and forwards identity with a shared secret."""

from __future__ import annotations

import datetime as dt
import hmac
import logging

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .ai import build_ai
from .config import Settings, settings
from .db import DB
from .roster import BY_EMAIL, Person
from .service import AppError, Service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("decisionos.api")


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractIn(In):
    notes: str = Field(max_length=20000)
    meeting_date: dt.date
    title: str | None = Field(default=None, max_length=120)


def create_app(s: Settings | None = None, db: DB | None = None, ai: object | None = None) -> FastAPI:
    s = s or settings()
    db = db or DB(s.db_path)
    ai = ai or build_ai(s)
    svc = Service(db=db, ai=ai, s=s)
    app = FastAPI(title="Decision OS API", version="1.0")
    app.state.svc = svc

    def user(x_internal_token: str = Header(default=""), x_user_email: str = Header(default="")) -> Person:
        if not s.internal_token or not hmac.compare_digest(x_internal_token, s.internal_token):
            raise AppError("UNAUTHENTICATED", "Missing or invalid internal token.", 401)
        p = BY_EMAIL.get(x_user_email.strip().lower())
        if p is None:
            raise AppError("UNAUTHENTICATED", "Unknown user.", 401)
        return p

    @app.exception_handler(AppError)
    async def app_error(_: Request, e: AppError):
        return JSONResponse(status_code=e.status, content={"code": e.code, "message": e.message, "details": e.details})

    @app.exception_handler(RequestValidationError)
    async def bad_input(_: Request, e: RequestValidationError):
        return JSONResponse(status_code=422, content={"code": "INVALID_INPUT", "message": "The request is not valid.",
                                                      "details": [x["msg"] for x in e.errors()[:5]]})

    @app.exception_handler(Exception)
    async def crash(_: Request, e: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"code": "INTERNAL", "message": "Something went wrong on the server."})

    @app.get("/health")
    def health():
        return {"ok": True, "ai": ai.status(), "version": db.version()}

    @app.get("/people")
    def people():
        return svc.people()

    @app.post("/extract")
    def do_extract(body: ExtractIn, me: Person = Depends(user)):
        return svc.ingest(body.notes, body.meeting_date, body.title, me)

    @app.get("/state")
    def state(since: int | None = None, me: Person = Depends(user)):
        v = db.version()
        if since is not None and since == v:
            return {"changed": False, "version": v}
        return {"changed": True, **svc.state(me)}

    @app.get("/meetings/{meeting_id}/source")
    def source(meeting_id: str, me: Person = Depends(user)):
        return svc.meeting_source(meeting_id)

    return app
