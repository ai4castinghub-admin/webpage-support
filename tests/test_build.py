import json
import re
from datetime import datetime, timedelta, timezone

from banner_pipeline.build import render_site
from banner_pipeline.common import isoformat


NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def item(index=1, expires=None):
    return {
        "id": f"item-{index}",
        "source_id": "phac",
        "source": "Public Health Agency of Canada",
        "title": f"Approved public health story {index}",
        "url": f"https://www.canada.ca/en/public-health/story-{index}.html",
        "published_at": isoformat(NOW - timedelta(days=1)),
        "expires_at": isoformat(expires or NOW + timedelta(days=7)),
        "selected": True,
        "evergreen": False,
    }


def embedded_payload(page):
    match = re.search(r'<script id="banner-data" type="application/json">(.*?)</script>', page, re.DOTALL)
    assert match
    return json.loads(match.group(1))


def test_site_contains_only_public_approved_fields():
    page = render_site([item()], now=NOW)
    payload = embedded_payload(page)
    assert set(payload["items"][0]) == {"id", "source", "title", "url", "published_at", "expires_at"}
    assert "source_id" not in page
    assert "SFTP" not in page
    assert "wp-content" not in page
    assert "Approved public health story 1" in page


def test_expired_items_build_empty_message_state():
    page = render_site([item(expires=NOW - timedelta(seconds=1))], now=NOW)
    assert embedded_payload(page)["items"] == []
    assert "No current featured updates" in page


def test_site_limits_output_to_five_items():
    page = render_site([item(index) for index in range(1, 7)], now=NOW)
    assert len(embedded_payload(page)["items"]) == 5


def test_site_is_self_contained_and_external_links_are_safe():
    page = render_site([item()], now=NOW)
    assert "<style>" in page and "<script>" in page
    assert 'target="_blank"' in page
    assert 'rel="noopener noreferrer"' in page
    assert "fetch(" not in page

