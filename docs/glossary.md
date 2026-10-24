# Glossary

Plain-language definitions of the terms used in this project.

| Term | Meaning |
|---|---|
| **Adapter** | A Python module in `scrapers/` that knows how to read one career-site *platform*. One adapter serves every employer on that platform. |
| **Platform / ATS** | The software an employer uses to publish jobs (Workday, UltiPro, Greenhouse...). "ATS" means applicant tracking system. |
| **Board URL** | The address of an employer's job listing page or feed, stored on the Employer row. |
| **JobRecord** | The standard "form" every adapter fills in for a job (title, URL, location...). Defined in `scrapers/base.py`. |
| **Normalized** | Converted to one common shape, so the rest of the code does not care where a job came from. |
| **Job (model)** | The same standard form as a database table. A `JobRecord` becomes a `Job` row when saved. |
| **Model** | A Python class in `jobs/models.py` that describes a database table. |
| **ORM** | Object-relational mapper: Django's way of reading and writing database rows as Python objects, without writing SQL. |
| **Migration** | A numbered file describing one change to the database structure. See [schema.md](schema.md). |
| **`makemigrations`** | Writes a new migration file from your model changes. Does not change the database. |
| **`migrate`** | Applies unapplied migrations to the database. |
| **Django project / app** | The project (`config/`) holds settings and URL routing. The app (`jobs/`) holds the models, pages and commands for one feature area. |
| **Admin** | Django's built-in management site at `/admin/`, used here to add employers and edit jobs. |
| **Management command** | A custom action run with `python manage.py <name>`: here `scrape` and `refilter`. |
| **Supabase** | The hosting service for the Postgres database. |
| **Session pooler** | The Supabase connection method that works over IPv4; its address goes in `.env` as `DATABASE_URL`. |
| **`.env`** | A file of secret settings (the database address and password). Never committed. |
| **venv** | A virtual environment: a private folder of Python packages for this project (`.venv/`). `(.venv)` at the start of your prompt means it is active. |
| **pip / requirements.txt** | `pip` installs Python packages; `requirements.txt` lists the ones this project needs. |
| **Sample (test data)** | A small invented response, written inside a test, that stands in for what a career site returns. No real scraped data is committed. See [testing.md](testing.md). |
| **pytest** | The test runner: runs every `test_*` function and reports failures. |
| **Parse vs fetch** | *Fetch* means getting data over the network. *Parse* means turning that data into records. Keeping them separate is what makes adapters testable offline. |
| **Prefilter** | Judging a job by its title and employer from the list alone, before spending a request on its details. |
| **Include keyword** | A word that a job title must contain to be considered. |
| **Whole-word match** | A term only matches as a complete word, so `java` does not match `javascript`. |
| **Score** | A count of how many preferred keywords a kept job contains. Used for sorting; never to accept or reject. |
| **Flag** | A warning stored on a job, such as `arrangement unclear` or `no description`. |
| **Status** | Where a job stands: new, saved, applied, ignored or filtered. |
| **Gitignore** | A list of files git must never commit (secrets, personal config, scratch data). |
| **JSON** | A text format for structured data; most adapters read it. |
| **Atom/RSS feed** | An XML format for lists of items; Job Bank publishes its job search results this way. |
