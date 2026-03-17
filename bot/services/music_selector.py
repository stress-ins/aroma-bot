"""Background music selector for video reels.

Selects a music track from the local library based on mood.
Actual MP3 files are managed separately; the selector works from a
``tracks.json`` manifest and gracefully returns ``None`` when the
physical file is missing.
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

MUSIC_DIR = Path(__file__).parent.parent.parent / "assets" / "music"
TRACKS_MANIFEST = MUSIC_DIR / "tracks.json"


def _load_manifest() -> list[dict]:
    """Load tracks manifest, returning empty list on any error."""
    if not TRACKS_MANIFEST.exists():
        logger.debug("Music manifest not found at %s", TRACKS_MANIFEST)
        return []
    try:
        data = json.loads(TRACKS_MANIFEST.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        logger.warning("Failed to parse music manifest", exc_info=True)
    return []


async def select_music(mood: str) -> Path | None:
    """Select a background music track matching the *mood*.

    Supported moods: calm, uplifting, contemplative, energetic, warm, mysterious.

    Returns the path to an existing MP3 file, or ``None`` if no matching
    track is found or the file does not exist on disk.
    """
    tracks = _load_manifest()
    if not tracks:
        return None

    mood_lower = mood.lower().strip()

    # Filter tracks whose mood list contains the requested mood
    matching = [
        t for t in tracks
        if isinstance(t.get("mood"), list) and mood_lower in [m.lower() for m in t["mood"]]
    ]

    if not matching:
        logger.debug("No music tracks match mood=%r", mood)
        return None

    # Pick a random matching track
    chosen = random.choice(matching)
    track_path = MUSIC_DIR / chosen["file"]

    if not track_path.exists():
        logger.debug("Music track file missing: %s", track_path)
        return None

    logger.info("Selected music track %s for mood=%r", chosen["file"], mood)
    return track_path


def list_tracks() -> list[dict]:
    """List all available music tracks with metadata.

    Each entry includes the manifest metadata plus an ``available`` boolean
    indicating whether the physical file exists.
    """
    tracks = _load_manifest()
    result = []
    for t in tracks:
        entry = dict(t)
        entry["available"] = (MUSIC_DIR / t.get("file", "")).exists() if t.get("file") else False
        result.append(entry)
    return result
