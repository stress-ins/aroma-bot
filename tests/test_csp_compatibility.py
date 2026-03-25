"""Verify Content-Security-Policy does not block resources used by the app.

Parses index.html for external <script>, <link>, <img> tags and checks that
every origin is whitelisted in the CSP returned by the FastAPI middleware.
Also checks that JS code using blob:/data: URLs has matching CSP directives,
and that the nginx config CSP stays in sync with the app CSP.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT / "miniapp" / "index.html"
NGINX_CONF = ROOT / "deploy" / "nginx-miniapp.conf"
JS_DIR = ROOT / "miniapp" / "static"


# ── helpers ──────────────────────────────────────────────────────────────


def _parse_csp(csp_string: str) -> dict[str, set[str]]:
    """Parse a CSP header string into {directive: {values}}."""
    directives: dict[str, set[str]] = {}
    for part in csp_string.split(";"):
        tokens = part.strip().split()
        if not tokens:
            continue
        directives[tokens[0]] = set(tokens[1:])
    return directives


def _get_app_csp() -> str:
    """Extract the CSP string from miniapp_server.py source code."""
    src = (ROOT / "miniapp_server.py").read_text()
    # Find Content-Security-Policy value — concatenated string literals
    match = re.search(
        r'["\']Content-Security-Policy["\'].*?\n(.*?)(?:\n\s*\))',
        src,
        re.DOTALL,
    )
    assert match, "Could not find CSP in miniapp_server.py"
    raw = match.group(1)
    # Join Python string concatenation: "abc" "def" → "abcdef"
    parts = re.findall(r'"([^"]*)"', raw)
    return "".join(parts)


def _get_nginx_csp() -> str:
    """Extract CSP string from nginx config."""
    text = NGINX_CONF.read_text()
    match = re.search(r'Content-Security-Policy\s+"([^"]+)"', text)
    assert match, "Could not find CSP in nginx config"
    return match.group(1)


class _ResourceCollector(HTMLParser):
    """Collect external resource URLs from HTML."""

    def __init__(self):
        super().__init__()
        self.resources: list[tuple[str, str]] = []  # (tag_type, url)

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "script" and (src := attrs_dict.get("src", "")):
            if src.startswith("http"):
                self.resources.append(("script-src", src))
        elif tag == "link" and attrs_dict.get("rel") == "stylesheet":
            href = attrs_dict.get("href", "")
            if href.startswith("http"):
                self.resources.append(("style-src", href))
        elif tag == "link" and attrs_dict.get("rel") == "preconnect":
            href = attrs_dict.get("href", "")
            if href.startswith("http"):
                self.resources.append(("connect-src", href))
        elif tag == "img" and (src := attrs_dict.get("src", "")):
            if src.startswith("http"):
                self.resources.append(("img-src", src))


def _origin(url: str) -> str:
    """https://cdn.example.com/path → https://cdn.example.com"""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _is_allowed(csp: dict[str, set[str]], directive: str, url: str) -> bool:
    """Check if url is allowed under the given CSP directive."""
    values = csp.get(directive, set())
    # Also check default-src as fallback (except for style-src, script-src
    # which don't fall back when explicitly set)
    if not values:
        values = csp.get("default-src", set())

    origin = _origin(url)
    scheme = urlparse(url).scheme + ":"  # "https:"

    for v in values:
        if v == "'self'":
            continue
        if v in ("https:", "http:") and scheme == v:
            return True
        if v == "*":
            return True
        if origin.endswith(v) or v == origin or url.startswith(v):
            return True
        # Wildcard subdomain: *.example.com
        if v.startswith("*."):
            domain = v[2:]
            if urlparse(url).netloc.endswith(domain):
                return True
    return False


def _scheme_allowed(csp: dict[str, set[str]], directive: str, scheme: str) -> bool:
    """Check if a scheme (blob:, data:) is allowed in a CSP directive."""
    values = csp.get(directive, set())
    if not values:
        values = csp.get("default-src", set())
    return scheme in values


# ── tests ────────────────────────────────────────────────────────────────


class TestCspCompatibility:
    """CSP must allow all resources actually used by the miniapp."""

    def test_index_html_resources_allowed_by_csp(self):
        """Every external URL in index.html must be whitelisted in CSP."""
        csp_str = _get_app_csp()
        csp = _parse_csp(csp_str)

        html = INDEX_HTML.read_text()
        collector = _ResourceCollector()
        collector.feed(html)

        blocked = []
        for directive, url in collector.resources:
            if not _is_allowed(csp, directive, url):
                blocked.append(f"{directive}: {url}")

        assert not blocked, (
            f"CSP blocks resources used in index.html:\n"
            + "\n".join(f"  - {b}" for b in blocked)
            + f"\n\nCurrent CSP: {csp_str}"
        )

    def test_blob_urls_allowed_for_images(self):
        """JS uses URL.createObjectURL for image previews — blob: must be in img-src."""
        js_files = list(JS_DIR.rglob("*.js"))
        uses_blob = any(
            "createObjectURL" in f.read_text() or "blob:" in f.read_text()
            for f in js_files
        )
        if not uses_blob:
            pytest.skip("No blob URL usage found in JS")

        csp = _parse_csp(_get_app_csp())
        assert _scheme_allowed(csp, "img-src", "blob:"), (
            "JS uses URL.createObjectURL() for image previews but CSP "
            "img-src does not include 'blob:'"
        )

    def test_data_urls_allowed_for_images(self):
        """CSS/JS uses data: URIs for inline SVGs — data: must be in img-src."""
        css_files = list(JS_DIR.rglob("*.css"))
        uses_data = any("data:image/" in f.read_text() for f in css_files)
        if not uses_data:
            pytest.skip("No data: URI usage found in CSS")

        csp = _parse_csp(_get_app_csp())
        assert _scheme_allowed(csp, "img-src", "data:"), (
            "CSS uses data: URIs for inline images but CSP "
            "img-src does not include 'data:'"
        )

    def test_inline_styles_allowed(self):
        """App uses inline styles — 'unsafe-inline' must be in style-src."""
        csp = _parse_csp(_get_app_csp())
        values = csp.get("style-src", set())
        assert "'unsafe-inline'" in values, (
            "App uses inline styles but style-src does not include 'unsafe-inline'"
        )

    def test_inline_scripts_allowed(self):
        """index.html has inline <script> for theme init — 'unsafe-inline' required."""
        html = INDEX_HTML.read_text()
        # Check for inline scripts (not just src= scripts)
        has_inline = bool(re.search(r"<script>", html))
        if not has_inline:
            pytest.skip("No inline scripts in index.html")

        csp = _parse_csp(_get_app_csp())
        values = csp.get("script-src", set())
        assert "'unsafe-inline'" in values, (
            "index.html has inline <script> but script-src "
            "does not include 'unsafe-inline'"
        )

    def test_nginx_csp_matches_app_csp(self):
        """nginx and FastAPI CSP must stay in sync."""
        app_csp = _parse_csp(_get_app_csp())
        nginx_csp = _parse_csp(_get_nginx_csp())

        mismatches = []
        all_directives = set(app_csp) | set(nginx_csp)
        for d in sorted(all_directives):
            app_vals = app_csp.get(d, set())
            nginx_vals = nginx_csp.get(d, set())
            if app_vals != nginx_vals:
                mismatches.append(
                    f"  {d}:\n"
                    f"    app:   {' '.join(sorted(app_vals)) or '(missing)'}\n"
                    f"    nginx: {' '.join(sorted(nginx_vals)) or '(missing)'}"
                )

        assert not mismatches, (
            "CSP mismatch between miniapp_server.py and nginx config:\n"
            + "\n".join(mismatches)
        )

    def test_font_files_do_not_need_external_csp(self):
        """If fonts are served locally, font-src should not reference CDNs."""
        csp = _parse_csp(_get_app_csp())
        font_values = csp.get("font-src", set())
        # No external CDN origins should be in font-src if fonts are local
        external = {v for v in font_values if v.startswith("http")}
        # Verify those CDNs are actually needed
        html = INDEX_HTML.read_text()
        for origin_url in external:
            assert origin_url in html or any(
                origin_url in f.read_text()
                for f in JS_DIR.rglob("*.css")
            ), (
                f"font-src allows '{origin_url}' but no font resource from "
                f"that origin is referenced in HTML or CSS — remove it from CSP"
            )
