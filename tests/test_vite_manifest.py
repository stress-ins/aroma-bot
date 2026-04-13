"""Tests for miniapp.vite_manifest — mtime-based cache invalidation."""

import json
import time
from pathlib import Path

import pytest


@pytest.fixture()
def manifest_dir(tmp_path):
    """Create a temporary static-dist directory with a Vite manifest."""
    dist = tmp_path / "static-dist"
    vite_dir = dist / ".vite"
    vite_dir.mkdir(parents=True)
    manifest = {
        "app.js": {"file": "assets/app-OLD123.js", "css": ["assets/app-OLD123.css"]},
    }
    manifest_path = vite_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return dist, manifest_path


def test_manifest_reloads_on_mtime_change(manifest_dir, monkeypatch):
    """When manifest.json is updated on disk, get_vite_assets returns new hashes."""
    dist, manifest_path = manifest_dir

    import miniapp.vite_manifest as vm

    monkeypatch.setattr(vm, "STATIC_DIST_DIR", dist)
    vm.invalidate_manifest_cache()

    # First read — should get OLD hash
    assets = vm.get_vite_assets()
    assert "OLD123" in assets["js"]
    assert "OLD123" in assets["css"]

    # Update manifest with new hash (bump mtime)
    time.sleep(0.05)  # ensure mtime differs
    new_manifest = {
        "app.js": {"file": "assets/app-NEW456.js", "css": ["assets/app-NEW456.css"]},
    }
    manifest_path.write_text(json.dumps(new_manifest))

    # Second read — should pick up NEW hash without explicit invalidation
    assets2 = vm.get_vite_assets()
    assert "NEW456" in assets2["js"], f"Expected new hash, got {assets2['js']}"
    assert "NEW456" in assets2["css"], f"Expected new hash, got {assets2['css']}"


def test_manifest_missing_falls_back_to_dev(tmp_path, monkeypatch):
    """When no manifest exists, dev-mode paths are returned."""
    import miniapp.vite_manifest as vm

    dist = tmp_path / "static-dist"
    dist.mkdir()
    monkeypatch.setattr(vm, "STATIC_DIST_DIR", dist)
    vm.invalidate_manifest_cache()

    assets = vm.get_vite_assets()
    assert assets["js"] == "/static/app.js"
    assert assets["css"] == "/static/app.css"


def test_invalidate_forces_reload(manifest_dir, monkeypatch):
    """invalidate_manifest_cache clears cached state."""
    dist, manifest_path = manifest_dir

    import miniapp.vite_manifest as vm

    monkeypatch.setattr(vm, "STATIC_DIST_DIR", dist)
    vm.invalidate_manifest_cache()

    assets = vm.get_vite_assets()
    assert "OLD123" in assets["js"]

    # Overwrite manifest (same mtime possible on fast filesystem)
    new_manifest = {
        "app.js": {"file": "assets/app-FORCE789.js", "css": ["assets/app-FORCE789.css"]},
    }
    manifest_path.write_text(json.dumps(new_manifest))

    # Without invalidation + same mtime, might return cached — but with invalidation, must reload
    vm.invalidate_manifest_cache()
    assets2 = vm.get_vite_assets()
    assert "FORCE789" in assets2["js"]
