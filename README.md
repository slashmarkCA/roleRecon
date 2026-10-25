# roleRecon

A personal job-discovery website scraping tool. You give it a list of employers; it checks their career pages
on demand, throws away the jobs that don't fit your rules, and shows the rest in a local web
page (job list on the left, full description on the right) where you can mark each job saved,
applied or ignored, and you dear user, then use judgement and apply manually. 

It is built with Python, Django and a Supabase (Postgres) database. Searching, scraping and filtering uses no AI, so it doesn't cost any tokens to run.  

![Pipeline](docs/diagrams/pipeline.svg)

Employers on a supported career-site platform are added with no code, just a row in the admin.
The supported platforms, what is not built yet (applying, a LinkedIn source, AI scoring, a web
login) and how everything works are in [docs/architecture.md](docs/architecture.md).

## Quick start

You need Python 3.12 and a Supabase project (or any Postgres database).

```
git clone <this repository> roleRecon && cd roleRecon
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env                                 # then edit: DATABASE_URL, SECRET_KEY, DEBUG
cp search_config.example.json search_config.json     # then edit your rules

python manage.py migrate                             # create the tables
python manage.py createsuperuser                     # login for /admin/
python manage.py runserver                           # http://127.0.0.1:8000/admin/
```

Then, in the admin, add an **Employer** (name, adapter, board URL, Options `{}`), and run:

```
python manage.py scrape                              # fetch + filter + save
python manage.py runserver                           # browse at http://127.0.0.1:8000/
```

The job page requires login. Use the same Django account created for the admin; if you are not
logged in, the page redirects to the admin login and returns you to the job page afterward.

`DATABASE_URL` should be Supabase's **session pooler** connection string; the reasons are in
[docs/schema.md](docs/schema.md). `SECRET_KEY` is Django's signing key; generate one with the
command shown in `.env.example`. Set `DEBUG=True` in `.env` for local development (it is off
when unset, which is the safe default).

## Starting again after a reboot

The database is hosted, so there is nothing to start except your own terminal.

1. Open a terminal in the project folder and activate the virtual environment:
   `source .venv/bin/activate`. The prompt then starts with `(.venv)`. (PyCharm's built-in
   terminal does this for you.)
2. Make sure you are online and that `.env` still exists in the project folder.
3. Refresh the jobs with `python manage.py scrape`, then browse with
   `python manage.py runserver` and open `http://127.0.0.1:8000/`.

If something fails: `pip install -r requirements.txt` (missing packages), `python manage.py
migrate` (database not up to date), or check `DATABASE_URL` in `.env`.

## Everyday commands

| Command | What it does |
|---|---|
| `python manage.py scrape` | For every active employer: fetch jobs, skip known ones, filter, and save new ones. Prints one summary line per employer. |
| `python manage.py refilter` | Re-apply your current `search_config.json` to stored jobs (no network). **Run it after editing the config.** |
| `python manage.py runserver` | Start the web page at `http://127.0.0.1:8000/` (admin at `/admin/`). Stop with Ctrl+C. |
| `python manage.py makemigrations jobs` | After changing `jobs/models.py`: write a migration file. |
| `python manage.py migrate` | Apply migrations to the database. |
| `python manage.py createsuperuser` | Create the admin login. |
| `python manage.py shell` | A Python prompt with the models loaded, for inspecting data. |
| `pytest` | Run the tests (offline). |

- After adding an employer: run `scrape` to fetch and filter its jobs.
- After editing `search_config.json`: run `refilter` to re-judge stored jobs; run `scrape` too
  only if you also want to fetch newly posted jobs.

## Project layout

```
roleRecon/
├── README.md                      this file
├── AGENTS.md                      instructions for AI coding assistants
├── LICENSE
├── manage.py                      Django's command-line entry point
├── requirements.txt               Python packages
├── .env / .env.example            SECRETS (git-ignored) / the same keys, empty (committed)
├── search_config.json             YOUR filter rules (git-ignored)
├── search_config.example.json     committed template for the file above
│
├── config/                        the Django PROJECT: settings and URL routing
├── jobs/                          the Django APP: models, admin, web page, commands
│   ├── models.py                  the Employer and Job tables
│   ├── admin.py, views.py, urls.py, templates/jobs/job_list.html
│   ├── migrations/                numbered database changes
│   └── management/commands/       scrape.py, refilter.py
│
├── scrapers/                      one ADAPTER module per platform; no Django imports
│   └── base.py                    JobRecord: the standard job form
├── rules/filters.py               load_config() and evaluate(): all filtering and scoring
├── tests/                         pytest tests (no network, no database)
├── data/                          (git-ignored) scratch space for samples and personal notes
└── docs/                          documentation (index below) and diagrams/
```

Not shown: `.venv/`, `.idea/`, `.vscode/`, `.gemini/`, `.agents/`, `.pytest_cache/`,
`__pycache__/` and `*.local.md` (local or generated and ignored).

## Documentation

| Page | Read it to learn |
|---|---|
| [docs/architecture.md](docs/architecture.md) | How a scrape works, the supported platforms (adapters), job statuses, current limits |
| [docs/config.md](docs/config.md) | Every setting in `search_config.json`, how filtering and scoring work |
| [docs/schema.md](docs/schema.md) | The database, migrations, and Supabase setup notes |
| [docs/testing.md](docs/testing.md) | Running tests; why sample data lives inside the tests |
| [docs/extending.md](docs/extending.md) | Adding an employer or a new platform adapter |
| [docs/glossary.md](docs/glossary.md) | Definitions of every term |

AI coding assistants should start with [AGENTS.md](AGENTS.md).
