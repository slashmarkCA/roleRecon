# Testing

Run all tests from the project folder with the virtual environment active:

```
pytest
```

Every test should pass. `pytest` finds functions named `test_...` in files named `test_*.py`
under [`tests/`](../tests/), calls each one, and reports pass or fail. The tests need no network
and no database.

## What is tested

| File | What it checks |
|---|---|
| `test_filters.py` | Every filter rule with small made-up jobs: exclusions, include keywords, whole-word matching (`java` vs `javascript`), locations, work arrangement, flags, scoring, and loading the config file. |
| `test_<platform>.py` (one per adapter) | The adapter's **parse** functions: given a small sample response, do we produce the right records? Also URL handling, such as extracting a Workday site name from a pasted job link. |

The management commands (`scrape`, `refilter`) and the web page are not covered by automated
tests. They are checked by running them against your own database.

## Samples live inside the tests

Each adapter test carries a **tiny, hand-written sample** of what the platform returns, with
invented jobs and an `example` employer. There are no saved copies of real career-site data in
the repository. Reasons:

- **Public-repository hygiene.** Real postings are other people's content and reflect one
  moment in time; they should not be committed, and neither should the employers you are
  targeting.
- **Tests stay fast, offline and deterministic.**
- **Anyone who clones the repository can run `pytest` and get green**, with nothing to
  download first.

The trade-off: a hand-written sample proves the parser handles the *shape* we know about, not
that a platform has not changed. To check a live site, run `python manage.py scrape` for an
employer on that platform and read the summary line and the "Filtered out" tab. If a platform
changes its format, capture a fresh response, update the sample in the test so it reflects the
new shape, and fix the parser until the test passes.

## Building a sample for a new adapter

When you are investigating a new platform you will want to look at real responses. Save them
under `data/`, which is git-ignored scratch space:

```
cd ~/dev/roleRecon
curl -sS -A "Mozilla/5.0" "<url>" -o data/sample.json
```

(`-s` hides progress output, `-S` still shows errors, `-A` sets the browser name some sites
require, `-o` names the output file. Run it from the project folder, because `data/sample.json`
is relative to where the terminal is. If a site resets curl's connection, try Python's
`requests` with a browser-style User-Agent instead.)

Read the sample, write the parser against it, then reduce the sample to the few fields your
parser reads, replace the real names and text with invented ones, and paste that into the
test file as a Python dictionary or string. That small invented sample is what gets committed.
