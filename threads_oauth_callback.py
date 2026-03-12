from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse


app = FastAPI()


@app.get("/")
async def root():
    return {"ok": True, "service": "threads-oauth-callback"}


@app.get("/threads/callback")
async def threads_callback(request: Request):
    return _render_oauth_callback_html("Threads", request)


@app.get("/instagram/callback")
async def instagram_callback(request: Request):
    return _render_oauth_callback_html("Instagram", request)


@app.get("/threads/deauthorize")
async def threads_deauthorize(request: Request):
    return JSONResponse(
        {
            "ok": True,
            "service": "threads-oauth-callback",
            "event": "deauthorize",
            "query": dict(request.query_params),
        }
    )


@app.post("/threads/delete")
async def threads_delete(request: Request):
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    confirmation_code = str(payload.get("confirmation_code", "threads-delete-request")).strip() or "threads-delete-request"
    return JSONResponse(
        {
            "url": "https://oauth.aromara.ru/threads/delete/status",
            "confirmation_code": confirmation_code,
        }
    )


@app.get("/threads/delete/status")
async def threads_delete_status():
    return JSONResponse({"ok": True, "status": "received"})


@app.get("/healthz")
async def healthz():
    return JSONResponse({"ok": True})


def _render_oauth_callback_html(service: str, request: Request) -> HTMLResponse:
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error", "")
    if error:
        return HTMLResponse(f"<h1>{service} OAuth error</h1><pre>{error}</pre>", status_code=400)
    if not code:
        return HTMLResponse("<h1>No code provided</h1>", status_code=400)

    html = (
        f"<h1>{service} OAuth code received</h1>"
        f"<p>State: <code>{state}</code></p>"
        f"<p>Code:</p><pre style=\"white-space:pre-wrap;overflow-wrap:anywhere\">{code}</pre>"
        "<p>Скопируй этот code и вернись в чат.</p>"
    )
    return HTMLResponse(html)
