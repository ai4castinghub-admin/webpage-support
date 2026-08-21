# Reviewed weekly news banner — GitHub Pages embed

A no-plugin WordPress homepage banner with weekly collection and a GitHub pull-request approval gate. GitHub Pages hosts one self-contained HTML page; WordPress contains only a permanent iframe.

## How it works

1. `collect.yml` runs Mondays at 8:00 a.m. `America/Toronto`, collects the previous seven days, and opens a review pull request. It never changes `main`.
2. A lead selects one to five candidates in `data/banner.yml`. The candidate lock prevents changing collected source, URL, or publication date.
3. Required checks and a lead approval must pass before merge.
4. A merge to `main` builds a self-contained page and deploys it with GitHub Pages.
5. The WordPress homepage iframe displays that approved page. No SFTP, child-theme access, WordPress plugin, runtime feed request, or AI service is required.

If no new candidates or unexpired prior selections exist, collection exits without opening an empty pull request. After published stories expire, the hosted page displays **No current featured updates**.

## 1. Create and configure the public GitHub repository

1. Create a public repository and upload this project at its root, including the hidden `.github` directory.
2. Open **Settings → Actions → General** and allow GitHub Actions for the repository.
3. Open **Settings → Pages** and select **GitHub Actions** as the publishing source.
4. Do not add SFTP credentials; this version does not use them.

The Pages address will normally be:

```text
https://GITHUB-ACCOUNT.github.io/REPOSITORY/
```

For an organization repository, use the organization name as `GITHUB-ACCOUNT`.

## 2. Configure sources

Edit `config/sources.yml`. Replace `example.org` in `own-blog`, update its `allowed_hosts`, and set `enabled: true`:

```text
https://YOUR-SITE.example/wp-json/wp/v2/posts
```

The WordPress posts endpoint normally requires no plugin. PHAC uses official feeds. The PHO parser fails rather than guessing if the News page markup becomes ambiguous. As an immediate PHO fallback, manually run **Collect weekly banner candidates** and complete all three optional PHO fields; that candidate receives the same immutable lock and lead review.

## 3. Protect the approval gate

In **Settings → Branches** or **Settings → Rules**, protect `main`:

- Require a pull request before merging.
- Require at least one approving review from a designated lead.
- Require **Validate banner review / validate**.
- Dismiss stale approvals after new commits.
- Block direct pushes and automation bypasses.
- Limit merge permission to designated leads.

If this belongs to an organization, copy `CODEOWNERS.example` to `.github/CODEOWNERS`, replace the placeholder team, and require code-owner review.

## 4. Run the first review and Pages deployment

1. Open **Actions → Collect weekly banner candidates → Run workflow**.
2. Open the pull request it creates.
3. In `data/banner.yml`, set `selected: true` for one to five items. You may shorten `title` to 110 characters or fewer.
4. Do not change `id`, `source_id`, `source`, `url`, or `published_at`.
5. Wait for validation, obtain lead approval, and merge.
6. Open the **Publish approved banner to GitHub Pages** run and copy its deployment URL.
7. Visit the Pages URL directly and test the controls before embedding it.

## 5. Embed on the WordPress homepage

Open `wordpress-homepage-embed.html` and replace `GITHUB-ACCOUNT` and `REPOSITORY` with the deployed Pages URL.

In WordPress:

1. Edit the homepage.
2. Add a **Custom HTML** block as the first block in the content area.
3. Paste the completed iframe snippet.
4. Preview before publishing.
5. Save, reopen the editor, and confirm WordPress preserved `iframe`, `sandbox`, `title`, and `style`.
6. Test the published homepage in a private/incognito window.

The banner is fixed at 156 pixels high to work across origins without a parent-page resizing script. It appears below the University theme header because the available HTML area is page-level.

If WordPress removes the iframe or the browser blocks it, stop and ask the University web administrator to permit or place this exact iframe. There is no reliable automatic page-level fallback without iframe permission.

## 6. Acceptance checks

- Test desktop and mobile layouts with no iframe scrollbars or clipping.
- Use `Tab`, `Shift+Tab`, `Enter`, and the banner buttons without a mouse.
- Test browser zoom at 200% and operating-system reduced motion.
- Confirm external stories open in a new tab.
- Confirm one item hides unnecessary controls and five items rotate every eight seconds.
- Confirm expired content becomes **No current featured updates**.
- Confirm an unreviewed branch cannot change the live Pages deployment.

## Local verification

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m banner_pipeline.collect
python -m banner_pipeline.validate
python -m banner_pipeline.build
```

The generated self-contained page is `build/site/index.html`. Tests use saved fixtures; only live collection requires network access. Validation intentionally fails until a lead selects at least one candidate.

## Operational notes

- Configure GitHub Actions failure notifications for repository maintainers.
- Normal items expire no later than 14 days after collection; `evergreen: true` requires an explicit lead decision.
- The published page contains only approved public headline fields. It contains no repository secrets or private review fields.
- This is a headline/link banner, not an emergency-alert system or source of medical advice.
