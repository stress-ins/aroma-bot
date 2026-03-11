from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot.services.drafts_store import get_draft, list_recent_drafts, update_draft
from bot.services.miniapp_presenter import filter_drafts, serialize_draft


BASE_DIR = Path(__file__).parent
MINIAPP_DIR = BASE_DIR / "miniapp"
STATIC_DIR = MINIAPP_DIR / "static"

app = FastAPI()

app.mount("/miniapp/static", StaticFiles(directory=STATIC_DIR), name="miniapp-static")


class DraftStatusPayload(BaseModel):
    status: str


class DraftFeedbackPayload(BaseModel):
    feedback: str


@app.get("/")
async def root():
    return {"ok": True, "service": "threads-oauth-callback"}


@app.get("/miniapp")
async def miniapp_index():
    return FileResponse(MINIAPP_DIR / "index.html")


@app.get("/miniapp/healthz")
async def miniapp_healthz():
    return JSONResponse({"ok": True, "service": "miniapp"})


@app.get("/miniapp/api/drafts")
async def miniapp_drafts(
    limit: int = Query(default=50, ge=1, le=200),
    kind: str = "",
    status: str = "",
    feedback: str = "",
    query: str = "",
):
    drafts = list_recent_drafts(limit=200)
    filtered = filter_drafts(
        drafts,
        kind=kind,
        status=status,
        feedback=feedback,
        query=query,
    )
    return {
        "items": [serialize_draft(record) for record in filtered[:limit]],
        "total": len(filtered),
    }


@app.get("/miniapp/api/drafts/{draft_id}")
async def miniapp_draft_detail(draft_id: str):
    draft = get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return serialize_draft(draft)


@app.post("/miniapp/api/drafts/{draft_id}/status")
async def miniapp_update_status(draft_id: str, payload: DraftStatusPayload):
    status = payload.status.strip().lower()
    if status not in {"draft", "in_review", "approved", "published"}:
        raise HTTPException(status_code=400, detail="invalid_status")
    draft = update_draft(draft_id, status=status)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return serialize_draft(draft)


@app.post("/miniapp/api/drafts/{draft_id}/feedback")
async def miniapp_update_feedback(draft_id: str, payload: DraftFeedbackPayload):
    feedback = payload.feedback.strip().lower()
    if feedback not in {"", "worked", "missed"}:
        raise HTTPException(status_code=400, detail="invalid_feedback")
    draft = update_draft(draft_id, feedback=feedback)
    if not draft:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return serialize_draft(draft)


@app.get("/threads/callback")
async def threads_callback(request: Request):
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error", "")
    if error:
        return HTMLResponse(f"<h1>Threads OAuth error</h1><pre>{error}</pre>", status_code=400)
    if not code:
        return HTMLResponse("<h1>No code provided</h1>", status_code=400)

    html = (
        "<h1>Threads OAuth code received</h1>"
        f"<p>State: <code>{state}</code></p>"
        f"<p>Code:</p><pre style=\"white-space:pre-wrap;overflow-wrap:anywhere\">{code}</pre>"
        "<p>Скопируй этот code и вернись в чат.</p>"
    )
    return HTMLResponse(html)


@app.get("/healthz")
async def healthz():
    return JSONResponse({"ok": True})
