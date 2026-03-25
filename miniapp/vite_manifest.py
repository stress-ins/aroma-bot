"""Read Vite build manifest to resolve hashed asset filenames."""

from __future__ import annotations

import json
from pathlib import Path

_manifest: dict | None = None

STATIC_DIST_DIR = Path(__file__).parent / "static-dist"


def get_vite_assets() -> dict[str, str]:
    """Return ``{"js": "/static-dist/assets/app-XXXX.js", "css": "..."}``

    Falls back to raw source paths when no build manifest exists (dev mode).
    """
    global _manifest

    manifest_path = STATIC_DIST_DIR / ".vite" / "manifest.json"
    if not manifest_path.exists():
        # No production build — serve raw source files
        return {"js": "/static/app.js", "css": "/static/app.css"}

    if _manifest is None:
        _manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    entry = _manifest.get("app.js", {})
    js = f"/static-dist/{entry.get('file', 'assets/app.js')}"

    # CSS may be listed under entry's "css" key or as a separate "style.css" entry
    css_files = entry.get("css", [])
    if css_files:
        css = f"/static-dist/{css_files[0]}"
    elif "style.css" in _manifest:
        css = f"/static-dist/{_manifest['style.css']['file']}"
    else:
        css = ""
    return {"js": js, "css": css}


def invalidate_manifest_cache() -> None:
    """Force re-read of manifest on next call (useful after a new build)."""
    global _manifest
    _manifest = None
