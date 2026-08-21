from __future__ import annotations

import argparse
import json
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .common import canonical_url, clean_title, parse_datetime, stable_id


IMMUTABLE_FIELDS = ("id", "source_id", "source", "url", "published_at")
HTML_PATTERN = re.compile(r"<[^>]*>|&(?:lt|gt|#60|#62);", re.IGNORECASE)


class ValidationError(ValueError):
    pass


def _allowed_hosts(sources: list[dict]) -> dict[str, set[str]]:
    return {
        source["id"]: {host.lower() for host in source.get("allowed_hosts", [])}
        for source in sources
        if source.get("enabled", False)
    }


def validate(review: dict, lock: dict, sources: list[dict], require_selection: bool = True) -> list[dict]:
    errors: list[str] = []
    items = review.get("items")
    if not isinstance(items, list):
        raise ValidationError("items must be a list")
    try:
        generated = parse_datetime(review.get("generated_at"))
    except (TypeError, ValueError):
        raise ValidationError("generated_at must be an ISO-8601 timestamp")

    if review.get("generated_at") != lock.get("generated_at"):
        errors.append("generated_at does not match the candidate lock")
    locked = {item.get("id"): item for item in lock.get("items", [])}
    allowed = _allowed_hosts(sources)
    selected: list[dict] = []
    seen: set[str] = set()

    for index, item in enumerate(items):
        label = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        item_id = item.get("id")
        if item_id in seen:
            errors.append(f"{label} repeats id {item_id}")
        seen.add(item_id)
        original = locked.get(item_id)
        if not original:
            errors.append(f"{label} is not present in candidates.lock.json")
            continue
        for field in IMMUTABLE_FIELDS:
            if item.get(field) != original.get(field):
                errors.append(f"{label}.{field} is immutable and differs from the collected candidate")

        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{label}.title is required")
        elif title != clean_title(title) or HTML_PATTERN.search(title):
            errors.append(f"{label}.title must be plain text without HTML")
        elif len(title) > 110:
            errors.append(f"{label}.title exceeds 110 characters")

        try:
            url = canonical_url(item.get("url", ""))
            hostname = (urlparse(url).hostname or "").lower()
            if hostname not in allowed.get(item.get("source_id"), set()):
                errors.append(f"{label}.url host is not allowed for its source")
            if stable_id(url) != item_id:
                errors.append(f"{label}.id does not match its canonical URL")
        except (TypeError, ValueError):
            errors.append(f"{label}.url must be an absolute HTTPS URL")

        if not isinstance(item.get("selected"), bool):
            errors.append(f"{label}.selected must be true or false")
        if not isinstance(item.get("evergreen"), bool):
            errors.append(f"{label}.evergreen must be true or false")
        try:
            parse_datetime(item.get("published_at"))
        except (TypeError, ValueError):
            errors.append(f"{label}.published_at must be an ISO-8601 timestamp")

        if item.get("selected"):
            selected.append(item)
            try:
                expires = parse_datetime(item.get("expires_at"))
                if expires <= generated:
                    errors.append(f"{label}.expires_at must be after generated_at")
                if not item.get("evergreen") and expires > generated + timedelta(days=14):
                    errors.append(f"{label}.expires_at may be at most 14 days after generation unless evergreen is true")
            except (TypeError, ValueError):
                errors.append(f"{label}.expires_at is required for selected items")

    extra_lock_ids = set(locked) - seen
    if extra_lock_ids:
        errors.append("candidates may not be deleted; leave unwanted entries selected: false")
    if require_selection and not 1 <= len(selected) <= 5:
        errors.append(f"select between 1 and 5 items; found {len(selected)}")
    if errors:
        raise ValidationError("\n".join(f"- {message}" for message in errors))
    return selected


def load_and_validate(review_path: Path, lock_path: Path, sources_path: Path, require_selection: bool = True) -> list[dict]:
    review = yaml.safe_load(review_path.read_text(encoding="utf-8")) or {}
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    source_data = yaml.safe_load(sources_path.read_text(encoding="utf-8")) or {}
    return validate(review, lock, source_data.get("sources", []), require_selection=require_selection)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", default="data/banner.yml")
    parser.add_argument("--lock", default="data/candidates.lock.json")
    parser.add_argument("--sources", default="config/sources.yml")
    parser.add_argument("--allow-zero", action="store_true")
    args = parser.parse_args()
    try:
        selected = load_and_validate(Path(args.review), Path(args.lock), Path(args.sources), not args.allow_zero)
    except (OSError, json.JSONDecodeError, yaml.YAMLError, ValidationError) as exc:
        print(f"Validation failed:\n{exc}")
        return 1
    print(f"Validated {len(selected)} selected banner item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

