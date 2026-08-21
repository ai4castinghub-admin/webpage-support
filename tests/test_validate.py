from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from banner_pipeline.common import isoformat, stable_id
from banner_pipeline.validate import ValidationError, validate


NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
URL = "https://www.canada.ca/en/public-health/story.html"


def documents(count=1):
    items = []
    for index in range(count):
        url = URL + f"?item={index}"
        items.append({
            "id": stable_id(url), "source_id": "phac", "source": "PHAC",
            "title": f"Public health story {index}", "url": url,
            "published_at": isoformat(NOW - timedelta(days=1)), "selected": True,
            "expires_at": isoformat(NOW + timedelta(days=14)), "evergreen": False,
        })
    review = {"generated_at": isoformat(NOW), "items": items}
    lock = {"generated_at": isoformat(NOW), "items": [
        {key: item[key] for key in ("id", "source_id", "source", "url", "published_at")} for item in items
    ]}
    sources = [{"id": "phac", "enabled": True, "allowed_hosts": ["www.canada.ca"]}]
    return review, lock, sources


def test_valid_selection_passes():
    review, lock, sources = documents()
    assert len(validate(review, lock, sources)) == 1


@pytest.mark.parametrize("count", [0, 6])
def test_requires_one_to_five(count):
    review, lock, sources = documents(count)
    with pytest.raises(ValidationError, match="select between 1 and 5"):
        validate(review, lock, sources)


def test_immutable_url_cannot_change():
    review, lock, sources = documents()
    review["items"][0]["url"] = "https://www.canada.ca/en/public-health/changed.html"
    with pytest.raises(ValidationError, match="immutable"):
        validate(review, lock, sources)


def test_rejects_html_and_long_expiration():
    review, lock, sources = documents()
    review["items"][0]["title"] = "<script>alert(1)</script>"
    review["items"][0]["expires_at"] = isoformat(NOW + timedelta(days=15))
    with pytest.raises(ValidationError) as caught:
        validate(review, lock, sources)
    assert "plain text" in str(caught.value)
    assert "at most 14 days" in str(caught.value)

