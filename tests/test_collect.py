from pathlib import Path

import pytest

from datetime import datetime, timedelta, timezone

from banner_pipeline.collect import _candidate, build_review, parse_feed, parse_pho_html, parse_wordpress


FIXTURES = Path(__file__).parent / "fixtures"


def source(source_id, name, url):
    return {"id": source_id, "name": name, "url": url}


def test_parse_phac_feed_strips_tracking_parameters():
    items = parse_feed((FIXTURES / "phac.xml").read_bytes(), source("phac", "PHAC", "https://www.canada.ca/feed"))
    assert items[0]["title"] == "Weekly public health update"
    assert items[0]["url"] == "https://www.canada.ca/en/public-health/test-update.html"


def test_parse_pho_requires_dated_news_link():
    items = parse_pho_html((FIXTURES / "pho.html").read_text(), source("pho", "PHO", "https://www.publichealthontario.ca/en/About/News"))
    assert items[0]["published_at"] == "2026-08-19T00:00:00Z"
    with pytest.raises(ValueError, match="markup may have changed"):
        parse_pho_html("<html><a href='/en/About/News/2026/no-date'>Undated story</a></html>", source("pho", "PHO", "https://www.publichealthontario.ca/en/About/News"))


def test_parse_wordpress_decodes_title():
    items = parse_wordpress((FIXTURES / "wordpress.json").read_text(), source("blog", "Our Blog", "https://example.org/wp-json/wp/v2/posts"))
    assert items[0]["title"] == "Our & community update"


def test_malformed_wordpress_fails_closed():
    with pytest.raises(ValueError):
        parse_wordpress("{}", source("blog", "Our Blog", "https://example.org/wp-json/wp/v2/posts"))


def test_manual_candidate_uses_same_review_and_lock(monkeypatch):
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    pho = source("pho-news", "Public Health Ontario", "https://www.publichealthontario.ca/en/About/News")
    pho.update({"enabled": True, "type": "pho_html"})
    manual = _candidate(
        pho, "Official PHO update",
        "https://www.publichealthontario.ca/en/About/News/2026/08/official-update",
        now - timedelta(days=1),
    )
    monkeypatch.setattr("banner_pipeline.collect.fetch_source", lambda _: [])
    review, lock, errors, successful = build_review([pho], [], now, 7, [manual])
    assert not errors and successful == 1
    assert review["items"][0]["title"] == "Official PHO update"
    assert lock["items"][0]["url"] == manual["url"]
