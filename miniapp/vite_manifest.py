"""Read Vite build manifest to resolve hashed asset filenames.

The manifest is re-read from disk when the file changes (based on mtime),
ensuring that a new Vite build is picked up without requiring a full process
restart.  The file is tiny (<1 KB), so the overhead is negligible.
"""

from __future__ import annotations

import json
from pathlib import Path

_manifest: dict | None = None
_manifest_mtime: float = 0.0

STATIC_DIST_DIR = Path(__file__).parent / "static-dist"


def _load_manifest() -> dict | None:
    """Return the parsed manifest, re-reading from disk if the file changed."""
    global _manifest, _manifest_mtime

    manifest_path = STATIC_DIST_DIR / ".vite" / "manifest.json"
    if not manifest_path.exists():
        _manifest = None
        _manifest_mtime = 0.0
        return None

    try:
        current_mtime = manifest_path.stat().st_mtime
    except OSError:
        return _manifest  # stat failed — return stale cache

    if _manifest is None or current_mtime != _manifest_mtime:
        _manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _manifest_mtime = current_mtime

    return _manifest


def get_vite_assets() -> dict[str, str]:
    """Return ``{"js": "/static-dist/assets/app-XXXX.js", "css": "..."}``

    Falls back to raw source paths when no build manifest exists (dev mode).
    """
    manifest = _load_manifest()
    if manifest is None:
        # No production build — serve raw source files
        return {"js": "/static/app.js", "css": "/static/app.css"}

    entry = manifest.get("app.js", {})
    js = f"/static-dist/{entry.get('file', 'assets/app.js')}"

    # CSS may be listed under entry's "css" key or as a separate styles entry
    css_files = entry.get("css", [])
    if css_files:
        css = f"/static-dist/{css_files[0]}"
    elif "app.css" in manifest:
        css = f"/static-dist/{manifest['app.css']['file']}"
    elif "style.css" in manifest:
        css = f"/static-dist/{manifest['style.css']['file']}"
    else:
        css = ""
    return {"js": js, "css": css}


def invalidate_manifest_cache() -> None:
    """Force re-read of manifest on next call (useful after a new build)."""
    global _manifest, _manifest_mtime
    _manifest = None
    _manifest_mtime = 0.0
