"""Smoke tests for post-deploy verification.

These tests run against a live VPS to verify the deployment succeeded.
They are NOT part of CI — run manually after deploy:

    VPS_HOST=46.32.186.192 .venv/bin/python -m pytest tests/smoke/ -v

Or via SSH:
    ssh root@46.32.186.192 'systemctl is-active aroma-bot && systemctl is-active aroma-miniapp'
"""
from __future__ import annotations

import os
import subprocess

import pytest

VPS_HOST = os.getenv("VPS_HOST", "46.32.186.192")
VPS_USER = os.getenv("VPS_USER", "root")

pytestmark = pytest.mark.skipif(
    not os.getenv("VPS_HOST"),
    reason="VPS_HOST not set — smoke tests are manual post-deploy checks",
)


def _ssh(cmd: str, timeout: int = 15) -> str:
    result = subprocess.run(
        ["ssh", f"{VPS_USER}@{VPS_HOST}", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def test_bot_service_running():
    """aroma-bot systemd service is active."""
    status = _ssh("systemctl is-active aroma-bot")
    assert status == "active", f"aroma-bot status: {status}"


def test_miniapp_service_running():
    """aroma-miniapp systemd service is active."""
    status = _ssh("systemctl is-active aroma-miniapp")
    assert status == "active", f"aroma-miniapp status: {status}"


def test_miniapp_responds():
    """Miniapp healthz endpoint returns 200."""
    output = _ssh("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/healthz")
    assert output == "200", f"healthz returned: {output}"


def test_miniapp_index_served():
    """Miniapp serves index.html with safe area CSS."""
    output = _ssh("curl -s http://127.0.0.1:8091/ | head -30")
    assert "safe-area-inset" in output or "<!DOCTYPE" in output.upper(), "index.html not served properly"


def test_database_accessible():
    """SQLite database exists and is readable."""
    output = _ssh("cd /opt/aroma && .venv/bin/python -c \"from db.session import AsyncSessionLocal; print('ok')\"")
    assert "ok" in output, f"DB check failed: {output}"
