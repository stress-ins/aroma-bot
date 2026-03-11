from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse


app = FastAPI()


@app.get("/")
async def root():
    return {"ok": True, "service": "threads-oauth-callback"}


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
