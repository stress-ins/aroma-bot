"""Tests for bot.services.status_monitor."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from bot.services.status_monitor import (
    parse_rss_items,
    filter_fresh_items,
    check_status_feeds,
    _parse_date,
    _seen_guids,
)

_SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Anthropic Status</title>
    <item>
      <title>Elevated API Error Rates</title>
      <link>https://status.anthropic.com/incidents/abc123</link>
      <pubDate>Mon, 18 Mar 2026 14:30:00 +0000</pubDate>
      <guid>https://status.anthropic.com/incidents/abc123</guid>
      <description>Investigating elevated error rates.</description>
    </item>
    <item>
      <title>Old Incident</title>
      <link>https://status.anthropic.com/incidents/old999</link>
      <pubDate>Mon, 10 Mar 2025 10:00:00 +0000</pubDate>
      <guid>https://status.anthropic.com/incidents/old999</guid>
      <description>Resolved long ago.</description>
    </item>
  </channel>
</rss>
"""


class TestParseRssItems:
    def test_parses_items(self):
        items = parse_rss_items(_SAMPLE_RSS)
        assert len(items) == 2
        assert items[0]["title"] == "Elevated API Error Rates"
        assert items[0]["guid"] == "https://status.anthropic.com/incidents/abc123"
        assert items[0]["link"] == "https://status.anthropic.com/incidents/abc123"

    def test_invalid_xml_returns_empty(self):
        assert parse_rss_items("not xml at all") == []

    def test_missing_fields_default_to_empty(self):
        xml = """\
<?xml version="1.0"?>
<rss><channel><item><title>No link</title></item></channel></rss>
"""
        items = parse_rss_items(xml)
        assert len(items) == 1
        assert items[0]["link"] == ""
        assert items[0]["guid"] == ""  # no link fallback either


_SAMPLE_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Google Cloud Status</title>
  <entry>
    <title>Google Cloud Networking — disruption</title>
    <link href="https://status.cloud.google.com/incidents/abc456"/>
    <updated>2026-03-18T15:00:00Z</updated>
    <id>tag:status.cloud.google.com,2026:abc456</id>
    <content type="html">Network issue in us-east1.</content>
  </entry>
  <entry>
    <title>Old Cloud Incident</title>
    <link href="https://status.cloud.google.com/incidents/old888"/>
    <updated>2025-01-01T00:00:00Z</updated>
    <id>tag:status.cloud.google.com,2025:old888</id>
    <content type="html">Resolved.</content>
  </entry>
</feed>
"""


class TestParseAtomItems:
    def test_parses_atom_entries(self):
        items = parse_rss_items(_SAMPLE_ATOM, fmt="atom")
        assert len(items) == 2
        assert items[0]["title"] == "Google Cloud Networking — disruption"
        assert items[0]["link"] == "https://status.cloud.google.com/incidents/abc456"
        assert items[0]["guid"] == "tag:status.cloud.google.com,2026:abc456"
        assert items[0]["pubDate"] == "2026-03-18T15:00:00Z"

    def test_atom_with_no_entries(self):
        xml = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Empty</title></feed>'
        assert parse_rss_items(xml, fmt="atom") == []


class TestParseDate:
    def test_rfc2822(self):
        dt = _parse_date("Mon, 18 Mar 2026 14:30:00 +0000")
        assert dt.year == 2026 and dt.month == 3 and dt.hour == 14

    def test_iso8601(self):
        dt = _parse_date("2026-03-18T15:00:00Z")
        assert dt.year == 2026 and dt.hour == 15
        assert dt.tzinfo is not None

    def test_iso8601_with_offset(self):
        dt = _parse_date("2026-03-18T15:00:00+03:00")
        assert dt.hour == 15


class TestFilterFreshItems:
    def test_filters_old_items(self):
        items = parse_rss_items(_SAMPLE_RSS)
        now = datetime(2026, 3, 18, 20, 0, 0, tzinfo=timezone.utc)
        fresh = filter_fresh_items(items, max_age_hours=24, now=now)
        assert len(fresh) == 1
        assert fresh[0]["title"] == "Elevated API Error Rates"

    def test_all_old_returns_empty(self):
        items = parse_rss_items(_SAMPLE_RSS)
        now = datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        fresh = filter_fresh_items(items, max_age_hours=24, now=now)
        assert fresh == []

    def test_filters_atom_items_by_freshness(self):
        items = parse_rss_items(_SAMPLE_ATOM, fmt="atom")
        now = datetime(2026, 3, 18, 20, 0, 0, tzinfo=timezone.utc)
        fresh = filter_fresh_items(items, max_age_hours=24, now=now)
        assert len(fresh) == 1
        assert fresh[0]["title"] == "Google Cloud Networking — disruption"

    def test_items_without_pubdate_skipped(self):
        items = [{"title": "No date", "guid": "x"}]
        fresh = filter_fresh_items(items, now=datetime.now(timezone.utc))
        assert fresh == []


class TestCheckStatusFeeds:
    @pytest.fixture(autouse=True)
    def _clear_seen(self):
        _seen_guids.clear()
        yield
        _seen_guids.clear()

    @pytest.mark.asyncio
    async def test_new_incident_triggers_notification(self):
        mock_resp = MagicMock()
        mock_resp.text = _SAMPLE_RSS
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("bot.services.status_monitor.httpx.AsyncClient") as mock_client_cls,
            patch("bot.services.status_monitor.notify_owner_throttled") as mock_notify,
            patch("bot.services.status_monitor.filter_fresh_items") as mock_filter,
        ):
            mock_client = MagicMock()

            async def fake_get(url):
                return mock_resp

            mock_client.get = fake_get
            mock_client.__aenter__ = lambda self: _async_return(mock_client)
            mock_client.__aexit__ = lambda self, *a: _async_return(None)
            mock_client_cls.return_value = mock_client

            call_count = [0]

            def make_items(*args, **kwargs):
                call_count[0] += 1
                return [
                    {
                        "title": "Test Incident",
                        "link": f"https://example.com/inc/{call_count[0]}",
                        "pubDate": "Mon, 18 Mar 2026 14:30:00 +0000",
                        "guid": f"guid-{call_count[0]}",
                        "description": "desc",
                    }
                ]

            mock_filter.side_effect = make_items

            await check_status_feeds()

            # 6 feeds × 1 unique item each = 6 notifications
            assert mock_notify.call_count == 6
            text = mock_notify.call_args_list[0][0][0]
            assert "Test Incident" in text

    @pytest.mark.asyncio
    async def test_deduplication_skips_seen_guids(self):
        _seen_guids.add("guid-dup")

        mock_resp = MagicMock()
        mock_resp.text = _SAMPLE_RSS
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("bot.services.status_monitor.httpx.AsyncClient") as mock_client_cls,
            patch("bot.services.status_monitor.notify_owner_throttled") as mock_notify,
            patch("bot.services.status_monitor.filter_fresh_items") as mock_filter,
        ):
            mock_client = MagicMock()

            async def fake_get(url):
                return mock_resp

            mock_client.get = fake_get
            mock_client.__aenter__ = lambda self: _async_return(mock_client)
            mock_client.__aexit__ = lambda self, *a: _async_return(None)
            mock_client_cls.return_value = mock_client

            mock_filter.return_value = [
                {
                    "title": "Already seen",
                    "link": "https://example.com/inc/dup",
                    "pubDate": "Mon, 18 Mar 2026 14:30:00 +0000",
                    "guid": "guid-dup",
                    "description": "desc",
                }
            ]

            await check_status_feeds()
            assert mock_notify.call_count == 0


async def _async_return(val):
    return val
