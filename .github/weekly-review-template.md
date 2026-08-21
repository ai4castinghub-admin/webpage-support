## Lead review required

This pull request cannot publish by itself. A lead must review `data/banner.yml`, then merge it.

1. Set `selected: true` on one to five items.
2. Optionally shorten `title` to no more than 110 characters. Keep it factual.
3. Keep `evergreen: false` for normal news. Normal expiry cannot exceed 14 days.
4. Do not change `id`, `source_id`, `source`, `url`, or `published_at`.
5. Wait for **Validate banner review** to pass, then merge.

Unselected candidates must remain in the file with `selected: false`; the validation lock ensures collected facts cannot be silently replaced.

