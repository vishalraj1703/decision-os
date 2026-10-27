"""Decision OS API. Bound to localhost; the browser reaches it only through the Next.js server,
which authenticates the user (NextAuth) and forwards identity with a shared secret."""

from __future__ import annotations

import datetime as dt
import hmac
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
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


class ResolveIn(In):
    action: str = Field(max_length=40)
    value: str | None = Field(default=None, max_length=120)


class StatusIn(In):
    status: str = Field(max_length=20)
    reason: str | None = Field(default=None, max_length=200)


class SlackIn(In):
    days: int | None = None


class ClarifyIn(In):
    flag: str = Field(max_length=40)
    to: str = Field(max_length=120)  # roster id or email
    question: str = Field(max_length=400)


class ClockIn(In):
    date: dt.date | None = None


class ExtractIn(In):
    notes: str = Field(max_length=20000)
    meeting_date: dt.date
    title: str | None = Field(default=None, max_length=120)


def create_app(s: Settings | None = None, db: DB | None = None, ai: object | None = None) -> FastAPI:
    s = s or settings()
    db = db or DB(s.db_path)
    ai = ai or build_ai(s)
    svc = Service(db=db, ai=ai, s=s)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        sched = None
        if s.scheduler_enabled:
            from apscheduler.schedulers.background import BackgroundScheduler

            sched = BackgroundScheduler(timezone=s.timezone)
            sched.add_job(svc.run_check, "interval", minutes=s.scheduler_minutes, id="deadline-check",
                          next_run_time=dt.datetime.now(dt.timezone.utc), max_instances=1, coalesce=True)
            sched.start()
            log.info("deadline scheduler every %d min", s.scheduler_minutes)
        yield
        if sched:
            sched.shutdown(wait=False)

    app = FastAPI(title="Decision OS API", version="1.0", lifespan=lifespan)
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

    @app.post("/contradictions/{cid}/resolve")
    def resolve_conflict(cid: str, body: ResolveIn, me: Person = Depends(user)):
        return svc.resolve_conflict(me, cid, body.action)

    @app.patch("/items/{item_id}/status")
    def set_status(item_id: str, body: StatusIn, me: Person = Depends(user)):
        return svc.update_status(me, item_id, body.status, body.reason)

    @app.post("/notifications/read")
    def read_notes(me: Person = Depends(user)):
        svc.read_notifications(me)
        return {"ok": True}

    @app.post("/items/{item_id}/resolve")
    def resolve(item_id: str, body: ResolveIn, me: Person = Depends(user)):
        return svc.resolve_item(me, item_id, body.action, body.value)

    def manager(me: Person = Depends(user)) -> Person:
        if me.role != "manager":
            raise AppError("FORBIDDEN", "Managers only.", 403)
        return me

    @app.post("/admin/reset")
    def reset(me: Person = Depends(manager)):
        db.reset()
        with db.tx(bump=True) as c:
            c.execute("DELETE FROM meta WHERE key<>'version'")
        return {"ok": True}

    @app.post("/admin/seed-demo")
    def seed_demo(me: Person = Depends(manager)):
        """Wipe everything and load the two demo meetings (last week, then this week)."""
        from .config import ROOT

        db.reset()
        with db.tx(bump=True) as c:
            c.execute("DELETE FROM meta WHERE key<>'version'")
        out = []
        for f, d in (("demo_meeting_0.txt", "2026-10-19"), ("demo_meeting_1.txt", "2026-10-26")):
            notes = (ROOT / "fixtures" / f).read_text(encoding="utf-8").strip()
            out.append(svc.ingest(notes, dt.date.fromisoformat(d), None, me))
        return {"ok": True, "meetings": out}

    @app.post("/admin/run-check")
    def run_check(me: Person = Depends(manager)):
        return svc.run_check()

    @app.post("/admin/clock")
    def clock(body: ClockIn, me: Person = Depends(manager)):
        return svc.set_clock(me, body.date)

    @app.get("/demo-notes")
    def demo_notes(me: Person = Depends(user)):
        from .config import ROOT

        fx = ROOT / "fixtures"
        return [
            {"label": "last week's meeting", "date": "2026-10-19", "notes": (fx / "demo_meeting_0.txt").read_text(encoding="utf-8").strip()},
            {"label": "this week's meeting", "date": "2026-10-26", "notes": (fx / "demo_meeting_1.txt").read_text(encoding="utf-8").strip()},
        ]

    @app.get("/whatif/{item_id}")
    def whatif(item_id: str, me: Person = Depends(user)):
        return svc.whatif(me, item_id)

    @app.patch("/items/{item_id}/slack")
    def set_slack(item_id: str, body: SlackIn, me: Person = Depends(user)):
        return svc.set_slack(me, item_id, body.days)

    @app.post("/items/{item_id}/clarify")
    def send_clarify(item_id: str, body: ClarifyIn, me: Person = Depends(user)):
        return svc.send_clarify(me, item_id, body.flag, body.to, body.question)

    @app.get("/export.csv")
    def export_csv(me: Person = Depends(user)):
        return Response(svc.export_csv(me), media_type="text/csv; charset=utf-8",
                        headers={"content-disposition": 'attachment; filename="decision-os-actions.csv"'})

    @app.get("/export/jira.json")
    def export_jira(project: str = "DOS", me: Person = Depends(user)):
        key = "".join(ch for ch in project.upper() if ch.isalnum())[:10] or "DOS"
        return Response(json.dumps(svc.export_jira(me, key), indent=1, ensure_ascii=False), media_type="application/json",
                        headers={"content-disposition": 'attachment; filename="decision-os-jira.json"'})

    @app.get("/meetings/{meeting_id}/source")
    def source(meeting_id: str, me: Person = Depends(user)):
        return svc.meeting_source(meeting_id)

    return app
