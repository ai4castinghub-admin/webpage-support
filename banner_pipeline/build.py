from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import isoformat, parse_datetime, utc_now
from .validate import load_and_validate


TEMPLATE_PATH = Path(__file__).with_name("page_template.html")
PUBLIC_FIELDS = ("id", "source", "title", "url", "published_at", "expires_at")


def render_site(selected: list[dict], now=None, template_path: Path = TEMPLATE_PATH) -> str:
    """Return a self-contained banner page containing only approved public data."""
    now = now or utc_now()
    active = [item for item in selected if parse_datetime(item["expires_at"]) > now][:5]
    payload = {
        "generated_at": isoformat(now),
        "items": [{key: item[key] for key in PUBLIC_FIELDS} for item in active],
    }
    embedded_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = template_path.read_text(encoding="utf-8")
    marker = "__REVIEWED_BANNER_DATA__"
    if template.count(marker) != 1:
        raise ValueError("page template must contain exactly one banner-data marker")
    return template.replace(marker, embedded_json)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", default="data/banner.yml")
    parser.add_argument("--lock", default="data/candidates.lock.json")
    parser.add_argument("--sources", default="config/sources.yml")
    parser.add_argument("--output", default="build/site/index.html")
    args = parser.parse_args()

    selected = load_and_validate(Path(args.review), Path(args.lock), Path(args.sources))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_site(selected), encoding="utf-8")
    print(f"Built self-contained GitHub Pages banner at {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

