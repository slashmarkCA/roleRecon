# Extending the tool

## Add an employer

If the employer uses a platform that already has an adapter (see the table in
[architecture.md](architecture.md)), no code is needed.

For Workable, use the public account board URL (`https://apply.workable.com/<account>/`).
The adapter reads the public Markdown list and each selected posting's Markdown detail page.
If the board needs a location or other search filter, include its query parameters in the URL;
the adapter preserves them when requesting the list.

Tiger Analytics is a special case: its Canada-filtered cards are already embedded in the public
careers page, and each card links to a Workable posting. Use the `Tiger Analytics` adapter with
the current-openings URL; the page's client-side filter does not require Playwright.

Altis uses a custom Angular job portal. Its public JSON API can be called directly, so use the
`Altis` adapter with `https://jobportal.altis.com/`; Playwright is not required. To limit the
listing request to one or more exact location labels, add repeated `location` query parameters,
for example `?location=Toronto%2C+ON&location=Oshawa%2C+ON`.

SuccessFactors search pages may use either the traditional HTML results table or the public
Recruiting Marketing React widget. The SuccessFactors adapter detects the widget from the page,
then uses its `/services/recruiting/v1/jobs` endpoint and the board URL's search filters.

Employer Options are passed to each adapter's list and detail functions. For Phenom, use a
`phenom` object to set exact `location` facets and adjust `page_size` or `max_jobs`; see the
[Employer options example](schema.md#employer) for the shape and defaults.

JSearch is a paid-quota aggregator adapter. Set `OPENWEBNINJA_API_KEY` in `.env`, then configure
its Employer Options with explicit search queries, for example:

```json
{
  "queries": ["business analyst jobs in Toronto", "QA jobs in Ajax"],
  "country": "ca",
  "date_posted": "month",
  "max_pages": 1
}
```

Each search query costs up to `max_pages` request credits. JSearch is limited to 30 request
credits per scrape; the adapter rejects a configuration above that limit before sending any
requests. Keep the Employer inactive until you are ready to spend credits. The API key is read
from the environment and must not be stored in Employer Options.

1. Open the employer's career page and copy its URL. Find its platform in the adapter table in
   [architecture.md](architecture.md); the "Board URL looks like" column shows what to paste
   (for Workday, a link to a single job also works). If the platform is not in the table, see
   "Add an adapter" below.
2. Start the admin (`python manage.py runserver`, then `http://127.0.0.1:8000/admin/`) and add
   an **Employer**: a name, the matching adapter, the board URL, Options `{}` (or settings such
   as `{"location_override": "Toronto"}`), and Active ticked.
3. Run `python manage.py scrape`. The summary line shows how many jobs were found and kept.
4. Open the web page; the "Filtered out" tab shows what was rejected and why. If good jobs are
   being rejected, adjust [`search_config.json`](config.md) and run `python manage.py refilter`.

If a location comes back too vague to match (every job says "Canada"), use the
`location_override` option described in [config.md](config.md).

## Add an adapter for a new platform

Work in this order. Each step gives you something to check before the next one.

1. **Investigate.** In the browser's developer tools, Network tab, reload the career page and
   find the request that returns the job data. Prefer a JSON endpoint; failing that, static
   HTML; use Playwright only if nothing else works. Check that it works without logging in. If
   a site rejects `curl`, try Python's `requests` with a browser-style User-Agent.
2. **Capture samples.** From the project folder, save a list response and one job's detail
   response under `data/` with `curl` (see [testing.md](testing.md)).
3. **Write `scrapers/<platform>.py`** with:
   - pure parse functions that turn a saved response into `JobRecord`s or a detail dict;
   - `fetch_list(board_url, session=None)` returning a list of `JobRecord`s;
   - `fetch_detail(board_url, rec, session=None)` returning a dict (or `{}`).

   A minimal skeleton:

   ```python
   import requests
   from .base import JobRecord

   UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}

   def parse_list(data, board_url):
       return [JobRecord(source_job_id=str(j["id"]), url=j["url"], title=j["title"],
                         location=j.get("location", "")) for j in data["jobs"]]

   def fetch_list(board_url, session=None):
       session = session or requests.Session()
       r = session.get(board_url, headers=UA, timeout=30)
       r.raise_for_status()
       return parse_list(r.json(), board_url)

   def fetch_detail(board_url, rec, session=None):
       return {}  # or fetch the posting and return {"description": ..., ...}
   ```

   Be polite: a short pause between requests, an identifiable User-Agent, and no more requests
   than needed.
4. **Register it.** Add its name, display label, and module path to
   [`scrapers/registry.py`](../scrapers/registry.py). The registry supplies both the Employer
   choices in [`jobs/models.py`](../jobs/models.py) and adapter loading in
   [`scrape.py`](../jobs/management/commands/scrape.py). Then run
   `python manage.py makemigrations jobs` and `python manage.py migrate`
   ([what these do](schema.md)).
5. **Test it.** Write `tests/test_<platform>.py` (copy an existing one) containing a small
   invented sample response, as described in [testing.md](testing.md), and run `pytest`.
6. **Try it live.** Add an Employer in the admin and run `python manage.py scrape`.
7. **Record it.** Add a row to the adapter table in [architecture.md](architecture.md); that
   table is the one list of supported platforms.

## Plain HTML pages and browser-driven sites

Not every employer sits on a platform with a JSON endpoint. Pick the simplest method that
works, in this order, and write it as an ordinary adapter (same `fetch_list` / `fetch_detail`
contract, same `JobRecord`).

1. **A JSON or feed endpoint** (preferred). See above; fast, stable and cheap.
2. **Static HTML with `requests` + Beautiful Soup.** Use this when *View Source* in the browser
   shows the jobs in the page itself. Fetch the page, then pick out the repeating job elements
   with CSS selectors:

   ```python
   from bs4 import BeautifulSoup

   def parse_list(html, board_url):
       soup = BeautifulSoup(html, "html.parser")
       return [JobRecord(source_job_id=a["href"], url=a["href"], title=a.get_text(strip=True))
               for a in soup.select("ul.jobs li a")]
   ```

   Because the selectors differ for every site, keep them in the Employer's **Options** JSON
   (for example `{"list_selector": "ul.jobs li a"}`) so one generic adapter can serve many
   plain-page employers. The reserved adapter choice `html` is for this. (Today `scrape` only
   reads the `location_override` option itself and does not pass Options to adapters; doing so
   is part of building that generic adapter.)
3. **A real browser with Playwright**, only when the page builds its job list with JavaScript
   and no endpoint can be found, or when a site needs clicking, scrolling or a logged-in
   session (this is the route a LinkedIn source would take; the reserved choices `browser` and
   `linkedin` are for it). Rules of thumb:
   - Extract compact fields inside the browser (for example `locator.evaluate_all(...)`) and
     return only those. Do not return whole pages.
   - Never hand raw page content to an AI model; pass it only the few extracted fields.
   - Run the browser from a separate adapter module, so the rest of the app stays unaware of
     it, and keep it out of the tests (test the parsing of captured text instead).
   - Install the browser with `playwright install chromium` and add `playwright` to
     `requirements.txt` when you first need it.
   - Sites such as LinkedIn forbid automated access in their terms and can restrict accounts.
     Keep volume low and keep "find jobs" separate from any future "apply" step.

## Conventions

See [AGENTS.md](../AGENTS.md).
