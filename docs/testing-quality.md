# Measured test quality

Coverage is a map of unexercised code, not a correctness oracle. Independent
goldens/mutations (#41), real workerd/D1 (#40) and Chromium (#42) provide the
behavioral evidence. The core baseline below is measured with coverage.py
7.16.2, Node 22's built-in V8 coverage and Chromium via v8-to-istanbul 9.3.0.
The browser PR is this quality PR's stacked base so actual dashboard coverage
can be measured without copying its suite into another enormous diff. Rebase
onto main after #42 merges, then consolidate workflows once all suite PRs merge.

| Module | Statements/lines hit | Branches hit | Uncovered baseline |
| --- | ---: | ---: | --- |
| `cloudflare/worker.mjs` | 283/283 lines | 190/196 V8 ranges | 0 lines, 6 branches |
| `cloudflare/collector.mjs` | 130/130 lines | 78/82 V8 ranges | 0 lines, 4 branches |
| `cloudflare/landmask.mjs` | 86/86 lines | 28/31 V8 ranges | 0 lines, 3 branches |
| `static/index.html` inline script | 867/972 converted statements | 189/248 V8 ranges | 105 converted statements, 59 branches |
| `research/evaluate.py` | 122/144 statements | 38/52 branches | 22 statements, 14 branches |
| `api_server.py` | 205/248 statements | 37/54 branches | 43 statements, 17 branches |
| `config.py` | 16/16 statements | 2/2 branches | 0 statements/branches |
| `mqtt_client.py` | 156/164 statements | 36/42 branches | 8 statements, 6 branches |
| `prediction_service.py` | 68/84 statements | 11/18 branches | 16 statements, 7 branches |

V8-to-Istanbul statements are line based; V8 branch ranges are not an AST
enumeration of every JavaScript conditional. Python statement/branch coverage
uses static analysis. These different instruments must not be pooled into one
percentage. Node VM tests omit map initialization; browser measurement covers
the real inline script with the real Leaflet renderer. Raw per-scenario V8
reports are retained, standard range merging handles overlap, and every browser
case must supply exactly one dashboard report.

## Reproduce and enforce

Install `requirements-dev.txt`, `research/requirements.txt` and run `npm ci`.
Use a disposable PostgreSQL DSN as in `docs/testing.md` (#39). Then:

```sh
mkdir -p reports
export COVERAGE_FILE=reports/.coverage
python -m coverage run -m pytest tests research -q -ra --junitxml=reports/python.xml
python -m coverage json -o reports/python-coverage.json
python -m coverage xml -o reports/python-coverage.xml
python scripts/check_coverage.py python reports/python-coverage.json
npm run test:coverage
python scripts/check_coverage.py node reports/node.lcov
npm run test:browser
npm run report:browser-coverage
python scripts/check_coverage.py browser reports/browser-coverage.json
```

`.coveragerc` measures the services, demo data and all research source files,
including files not imported by the tests. The gate discovers root Python
services, recursive research Python modules, Cloudflare JavaScript modules and
static HTML/JavaScript assets independently of the baseline. Test files,
`conftest.py` and maintenance/build scripts under `scripts/` are excluded.
Every discovered source needs both a baseline entry and a coverage report;
unlisted report entries and stale baseline entries also fail. New root Python
modules must also be added to `.coveragerc`. New frontend modules fail until
the browser reporter measures them and their baselines are reviewed.
`tests/coverage-baseline.json` records **maximum uncovered counts per
module**, not an arbitrary passing percentage. Added covered code cannot mask
lost coverage by growing a denominator. Any increased uncovered count needs a
reviewed explanation and explicit baseline change. This is intentionally a
first measured baseline, not a claim of comprehensive testing. Deleting tests
that leave the same coverage can still pass, so mutation/oracle checks remain
essential.

Local covered run: 116 original Python cases in 0.96 s; adding gate regressions
gives 118 total Python cases (0.65 s without tracing). Node tracing ran 79 cases
in 224.52 ms. Twelve browser cases passed with coverage enabled. GitHub Python
3.11 timing/counts must be recorded after CI; local Python was 3.12.3.

## Representative mutation evidence

No general-purpose mutation dependency is added. Targeted campaigns are small
and explainable:

- #41: invalid speed, changed horizon, suppressed land flag and fabricated null
  projection: **4/4 detected**, with a passing baseline and assertions executed.
- #42: deleted real rendering notice, broken API request limit and browser
  fallback: **3/3 detected** using actual Chromium in temporary copies.
- #44: changed geographic bytes, exceeded bundle budget, broken container CMD:
  **3/3 detected**. Good image/source files remained intact.
- This PR: omitted required coverage and increased uncovered statements/branches
  fail the gate regression. This verifies enforcement, not model performance.

Scientific split/leakage/matching/bootstrap validation belongs to #16–#18.
No coverage result or synthetic test permits a forecasting accuracy claim.

## Combined verification (2026-10-14)

The dependency integration checkout runs 142 Python/PostgreSQL cases in 1.39 s,
83 Node cases in 227.92 ms, 12 workerd/D1 cases in 1.78 s and 12 Chromium
cases in 5.7 s. All required inventories match, with zero skipped or deselected
cases. These are local Python 3.12.3 and Node 22 measurements. Coverage gates
pass; independent scientific tests improve evaluate.py to 16 uncovered
statements and 10 branches, and that tighter baseline is recorded.
The required inventories enumerate behavior by testcase identity; a passing
subset is rejected independently of coverage percentages.
