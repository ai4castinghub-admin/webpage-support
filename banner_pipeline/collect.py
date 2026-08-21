from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

from .common import canonical_url, clean_title, isoformat, normalized_title, parse_datetime, stable_id, utc_now


DATE_PATTERN = re.compile(
    r"\b(?:Published\s+)?(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b",
    re.IGNORECASE,
)
USER_AGENT = "ReviewedNewsBanner/1.0 (+website content collection; weekly)"


def matches_topic(source: dict, *values: str) -> bool:
    """Apply optional source topic rules to normalized title/summary text.

    A rule matches when any configured phrase matches, or when every keyword
    group under ``all`` contributes at least one match. Sources without rules
    remain unfiltered.
    """
    rules = source.get("topic_rules")
    if not rules:
        return True
    haystack = " ".join(clean_title(value).lower() for value in values if value)
    for rule in rules:
        phrases = rule.get("any", [])
        if phrases and any(str(phrase).lower() in haystack for phrase in phrases):
            return True
        groups = rule.get("all", [])
        if groups and all(
            any(str(phrase).lower() in haystack for phrase in group)
            for group in groups
        ):
            return True
    return False


def _feed_date(entry: dict) -> datetime:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if value:
            try:
                return parsedate_to_datetime(value).astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    raise ValueError("feed entry has no parseable publication date")


def parse_feed(payload: bytes | str, source: dict) -> list[dict]:
    parsed = feedparser.parse(payload)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"invalid feed for {source['id']}: {parsed.bozo_exception}")
    items = []
    for entry in parsed.entries:
        try:
            title = clean_title(entry.get("title", ""))
            summary = clean_title(entry.get("summary") or entry.get("description") or "")
            url = canonical_url(entry.get("link", ""))
            published = _feed_date(entry)
            if not title or not matches_topic(source, title, summary):
                continue
            items.append(_candidate(source, title, url, published))
        except (TypeError, ValueError):
            continue
    if not items and not source.get("topic_rules"):
        raise ValueError(f"feed for {source['id']} contained no valid entries")
    return items


def parse_wordpress(payload: str, source: dict) -> list[dict]:
    records = json.loads(payload)
    if not isinstance(records, list):
        raise ValueError("WordPress response must be a JSON list")
    items = []
    for record in records:
        try:
            title = clean_title(record["title"]["rendered"])
            url = canonical_url(record["link"])
            published = parse_datetime(record.get("date_gmt") or record.get("date"))
            if title:
                items.append(_candidate(source, title, url, published))
        except (KeyError, TypeError, ValueError):
            continue
    if not items:
        raise ValueError(f"WordPress source {source['id']} contained no valid posts")
    return items


def parse_pho_html(payload: str, source: dict) -> list[dict]:
    """Extract only dated article links below PHO's /About/News/ path.

    This intentionally skips ambiguous cards instead of inventing metadata. A total
    failure raises an error so a PHO markup change is visible in Actions.
    """
    soup = BeautifulSoup(payload, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()
    listing_path = urlparse(source["url"]).path.rstrip("/").lower()

    for link in soup.select('a[href*="/About/News/"]'):
        href = link.get("href", "")
        try:
            url = canonical_url(urljoin(source["url"], href))
        except ValueError:
            continue
        if urlparse(url).path.rstrip("/").lower() == listing_path or url in seen:
            continue

        title = clean_title(link.get_text(" ", strip=True))
        if len(title) < 8:
            continue

        container = link
        date_value = None
        for _ in range(5):
            container = container.parent
            if container is None:
                break
            time_tag = container.find("time")
            if time_tag:
                date_value = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
            text = container.get_text(" ", strip=True)
            match = DATE_PATTERN.search(text)
            if not date_value and match:
                date_value = match.group(1)
            if date_value:
                break
        if not date_value:
            continue
        try:
            try:
                published = parse_datetime(date_value)
            except ValueError:
                published = datetime.strptime(date_value, "%d %B %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                published = datetime.strptime(date_value, "%d %b %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        items.append(_candidate(source, title, url, published))
        seen.add(url)

    if not items:
        raise ValueError("PHO parser found no unambiguous dated news links; the page markup may have changed")
    return items


def _candidate(source: dict, title: str, url: str, published: datetime) -> dict:
    return {
        "id": stable_id(url),
        "source_id": source["id"],
        "source": source["name"],
        "title": clean_title(title),
        "url": canonical_url(url),
        "published_at": isoformat(published),
        "selected": False,
        "expires_at": None,
        "evergreen": False,
    }


def fetch_source(source: dict, timeout: int = 30) -> list[dict]:
    params = {}
    if source["type"] == "wordpress":
        params = {"per_page": 20, "_fields": "link,date,date_gmt,title"}
    response = requests.get(
        source["url"], params=params, timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml, application/rss+xml, text/html"},
    )
    response.raise_for_status()
    if source["type"] == "rss":
        return parse_feed(response.content, source)
    if source["type"] == "wordpress":
        return parse_wordpress(response.text, source)
    if source["type"] == "pho_html":
        return parse_pho_html(response.text, source)
    raise ValueError(f"unsupported source type: {source['type']}")


def _load_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("items", []) if isinstance(data, dict) else []


def build_review(
    sources: list[dict], existing: list[dict], now: datetime, days: int,
    manual_candidates: list[dict] | None = None,
) -> tuple[dict, dict, list[str], int]:
    cutoff = now - timedelta(days=days)
    expiry = now + timedelta(days=14)
    candidates: list[dict] = list(manual_candidates or [])
    errors: list[str] = []
    successful_sources = 0

    for source in sources:
        if not source.get("enabled", False):
            continue
        try:
            candidates.extend(fetch_source(source))
            successful_sources += 1
        except Exception as exc:  # Per-source failure must not discard other sources.
            errors.append(f"{source['name']} ({source['id']}): {exc}")

    retained = []
    for item in existing:
        try:
            if item.get("selected") and parse_datetime(item.get("expires_at")) > now:
                retained.append(dict(item))
        except (TypeError, ValueError):
            continue

    recent = []
    for item in candidates:
        try:
            if parse_datetime(item["published_at"]) >= cutoff:
                item["expires_at"] = isoformat(expiry)
                recent.append(item)
        except ValueError:
            continue

    merged: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for item in retained + sorted(recent, key=lambda row: row["published_at"], reverse=True):
        url_key = canonical_url(item["url"])
        title_key = normalized_title(item["title"])
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        merged.append(item)

    generated_at = isoformat(now)
    review = {"generated_at": generated_at, "items": merged}
    lock = {
        "generated_at": generated_at,
        "items": [
            {key: item[key] for key in ("id", "source_id", "source", "url", "published_at")}
            for item in merged
        ],
    }
    return review, lock, errors, successful_sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="config/sources.yml")
    parser.add_argument("--review", default="data/banner.yml")
    parser.add_argument("--lock", default="data/candidates.lock.json")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    source_path, review_path, lock_path = map(Path, (args.sources, args.review, args.lock))
    source_data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    sources = source_data.get("sources", [])
    manual_candidates = []
    manual_url = os.environ.get("MANUAL_PHO_URL", "").strip()
    manual_title = os.environ.get("MANUAL_PHO_TITLE", "").strip()
    manual_date = os.environ.get("MANUAL_PHO_DATE", "").strip()
    if any((manual_url, manual_title, manual_date)):
        if not all((manual_url, manual_title, manual_date)):
            raise SystemExit("Manual PHO fallback requires title, URL, and publication date")
        pho_source = next((source for source in sources if source.get("id") == "pho-news"), None)
        if not pho_source:
            raise SystemExit("Manual PHO fallback requires the pho-news source configuration")
        manual_candidates.append(_candidate(pho_source, manual_title, manual_url, parse_datetime(manual_date)))

    review, lock, errors, successful_sources = build_review(
        sources, _load_existing(review_path), utc_now(), args.days, manual_candidates
    )
    if successful_sources == 0 and not manual_candidates:
        raise SystemExit("All enabled collectors failed:\n" + "\n".join(errors))

    if errors:
        print("::warning::Some collectors failed; manual review is required: " + " | ".join(errors))
    if not review["items"]:
        print("No new candidates or unexpired selections were found; leaving review files unchanged")
        return 0

    review_path.write_text(yaml.safe_dump(review, sort_keys=False, allow_unicode=True), encoding="utf-8")
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Prepared {len(review['items'])} review candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
