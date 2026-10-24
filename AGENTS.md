# AGENTS.md

roleRecon scrapes employers' career pages, filters the jobs with rules in `search_config.json`,
and shows the results in a local web page. Python 3.12, Django, Postgres (Supabase). The
human instructions, overview and file layout are in [README.md](README.md).

This is the canonical shared project instruction file. If an agent does not load `AGENTS.md`
automatically, configure that client to read it or ask it to do so. Avoid duplicate provider-
specific instruction files unless a client requires a small pointer.

## Private session notes

If a git-ignored `*.local.md` file exists in the repository root (for example
`HANDOFF.local.md`), read it first: it holds the current state, decisions and next steps. git clones
will not have it, so never depend on it.

## Commands

```
source .venv/bin/activate          # every command below assumes the venv is active
pytest                             # tests; offline, no database
python manage.py scrape            # fetch, filter and save jobs for every active employer
python manage.py refilter          # re-apply search_config.json to jobs already stored
python manage.py makemigrations jobs && python manage.py migrate   # after editing db schema models
python manage.py runserver         # web page at http://127.0.0.1:8000/
```

- Run `pytest` after code changes.
- After changing `jobs/models.py`: `makemigrations` then `migrate`.
- After adding an employer: run `scrape` to fetch and filter its jobs.
- After editing `search_config.json`: run `refilter` to re-evaluate stored jobs. Run `scrape`
  too only when you also want to fetch newly posted jobs.
- If you cannot run commands, give the person the exact command and ask for the output.
- The full command list is in the README.

## Where to look

Read only what the task needs.

| Task | Read |
|---|---|
| How a scrape works, the supported platforms, job statuses | [docs/architecture.md](docs/architecture.md), `jobs/management/commands/scrape.py` |
| Filter rules, config keys, scoring, "why was this job rejected" | [docs/config.md](docs/config.md), `rules/filters.py` |
| Database fields, migrations, Supabase | [docs/schema.md](docs/schema.md), `jobs/models.py` |
| Add an employer, or a new platform adapter (API, HTML or browser) | [docs/extending.md](docs/extending.md), the closest `scrapers/*.py` and its test |
| Run or write tests | [docs/testing.md](docs/testing.md) |
| The web page or admin | `jobs/views.py`, `jobs/templates/jobs/job_list.html`, `jobs/admin.py` |
| A term you do not know | [docs/glossary.md](docs/glossary.md) |

## Conventions

- **Adapters are per platform, not per employer.** Each module in `scrapers/` exposes
  `fetch_list` and `fetch_detail` and returns the standard `JobRecord`. Keep platform-specific
  and employer-specific values out of code; employer settings belong in the Employer row.
- **Keep parse functions free of network calls** so they can be tested offline.
- **Prefer a JSON endpoint** over HTML scraping, and HTML over a browser. Use Playwright only as
  a last resort and extract compact fields, never whole pages.
- **Be polite to career sites:** identify the client, pause between requests, fetch only what
  is needed.
- **Keep discovery and applying separate.** Applying, if added, reads only approved jobs.
- **Change the database only through migrations,** and write data through Django (admin, views,
  commands), not by hand in the database console.
- **No one-off or development-only code** unless there is a lasting need.
- When configuration keys or structure change, update the matching example in the same change.
  Keep `search_config.example.json` aligned with the supported keys and nesting, but use generic
  values; keep `.env.example` aligned with required variable names and blank or safe placeholder
  values. Never copy personal settings or secrets into examples. Validate example JSON.

## Security and data boundaries

- `.env`, `search_config.json`, any other personal config, `*.local.md` and everything under
  `data/` are git-ignored. Never print, read aloud or ask for the contents of `.env`.
- No scraped data in the repository. Tests use small invented samples with `example` employers;
  use generic names in code, docs and diagrams.
- Check `git status` before committing anything and confirm no personal files are staged.

## Documentation upkeep

Update the matching page in `docs/` when behaviour changes, and keep one source of truth per fact:
the supported-platform list lives in `docs/architecture.md`, config keys in `docs/config.md`,
fields in `docs/schema.md`. Link to those pages instead of repeating them.
