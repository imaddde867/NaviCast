# Testing NaviCast

Green CI proves only the contracts exercised below. Actual Chromium/Leaflet and
workerd/D1 checks now verify dashboard rendering and runtime contracts. They do
not establish forecast accuracy or production Cloudflare operation.
CI uses Python 3.11, Node 22, PostgreSQL 16, pinned Python requirements and
`npm ci --ignore-scripts`. It has read-only permissions, no production secrets,
and no deployment step (`check:deploy` is a dry run).

## Reproduce from a clean checkout

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt -r research/requirements.txt
npm ci --ignore-scripts
mkdir -p reports
docker run --rm -d --name navicast-test-postgres \
  -e POSTGRES_PASSWORD=local-test-only -e POSTGRES_DB=ais_project \
  -p 127.0.0.1:55432:5432 postgres:16
docker exec navicast-test-postgres pg_isready -U postgres -d ais_project
# Wait for pg_isready to succeed before proceeding.
export NAVICAST_TEST_DSN='host=127.0.0.1 port=55432 dbname=ais_project user=postgres password=local-test-only'
NAVICAST_REQUIRED_TESTS=1 python -m pytest tests research -q -ra \
  --durations=10 --junitxml=reports/python.xml
python scripts/check_test_report.py reports/python.xml tests/inventory/python.json
npm run test:ci
python scripts/check_test_report.py reports/node.xml tests/inventory/node.json
WRANGLER_SEND_METRICS=false npm run test:runtime
python scripts/check_test_report.py reports/runtime.xml tests/inventory/runtime.json
npx playwright install chromium
npm run test:browser
python scripts/check_test_report.py reports/browser.xml tests/inventory/browser.json
node scripts/check_projection_mutations.mjs
node scripts/check_browser_mutations.mjs
python scripts/check_research_mutations.py
WRANGLER_SEND_METRICS=false npm run check:deploy
WRANGLER_SEND_METRICS=false npm run check:bundle
bash -n start_navicast.sh
docker compose config --quiet
docker build -t navicast-check .
bash scripts/check_docker.sh
docker stop navicast-test-postgres
```

Use only a disposable database. PostgreSQL tests apply the actual `schema.sql`
to unique test schemas and drop only those schemas afterward. Without a DSN,
`python -m pytest -q -ra` intentionally skips four PostgreSQL cases for
convenient offline work; this is forbidden in CI by
the JUnit report guard. Required CI runs also reject deselection (`-k`, `-m`,
etc.). Reports list counts, skips, failures and test durations, and are uploaded
even when a test command fails. Missing, malformed, empty, skipped or failing
reports cannot pass the guard. Expected failures also count as skipped and need
an explicit policy change before inclusion in a required suite.

Required suites also compare the exact testcase identities in
`tests/inventory/*.json`. A nonempty passing subset or file-only wrapper report
cannot substitute for required scenarios. Inventories are reviewed suite
bookkeeping, not projection oracles: additions may pass without raising a total
count target; removing a required behavior needs an explicit inventory change.

## Current validation layers

The combined implementation runs 142 Python/PostgreSQL/research cases, 83 Node
cases, 12 workerd/D1 cases and 12 actual Chromium/Leaflet cases. Required
inventories are per-case contracts, not a target total. The five final CI jobs
also run coverage gates and ten targeted software/scientific mutation probes.
Commands above execute all suites and demo Docker startup; coverage reproduction
is in [testing-quality.md](testing-quality.md). Suite-specific architecture,
limitations and evidence are in [projection references](../tests/golden/README.md),
[testing-browser.md](testing-browser.md), [testing-runtime.md](testing-runtime.md),
[testing-infrastructure.md](testing-infrastructure.md), and
[testing-scientific.md](testing-scientific.md). Final CI timing and protection
rollout are in [testing-enforcement.md](testing-enforcement.md). A requirement-by-
requirement status audit is in [testing-acceptance.md](testing-acceptance.md).

Main protection requires all five checks and PRs, including administrator
enforcement. The deliberately failing #48 probe was blocked and closed
without merging; see the enforcement evidence. Source-ZIP regeneration remains
conditional on that exact input. Synthetic scientific checks permit no forecasting accuracy claim.

## Baseline audit

Measured on 2026-10-14 at `dca965c02e09247b62b69e19170531d5aa52d85e`
(main, including merged PR #38). Local Python was **3.12.3**, pytest 8.3.5,
NumPy 2.3.3, Node **22.23.1**, npm 9.2.0 and Wrangler 4.149.0. Python 3.11
compatibility must also be checked by CI; these local measurements do not prove
it. Times are runner-reported elapsed times, not GitHub job budgets.

| Check | Result before hardening | Time / measurement |
| --- | --- | --- |
| All Python, disposable PostgreSQL | 116 passed, 0 skipped, 0 failures | 0.64 s |
| Python without DSN | 113 passed, 3 skipped, 0 failures | 0.59 s |
| Node unit tests | 79 passed, 0 skipped/cancelled/todo, 0 failures | 188.46 ms |
| Wrangler dry run | Passed | 886.45 KiB upload, 561.06 KiB gzip |
| Shell syntax | Passed | Syntax check, no runtime exercise |
| Compose configuration | Passed | Configuration check, no services started |
| Docker build | Passed | BuildKit step times reported; total not recorded |

Build/configuration timing rerun, 2026-10-14: a detached clean checkout of the
same unchanged main `dca965c` used `npm ci --ignore-scripts`, then measured wall
elapsed time with `time.perf_counter` around each complete command. Every check
exited zero: Wrangler dry run **0.529808 s**, Bash syntax
**0.000981 s**, Compose config **0.026530 s** and
Docker build **0.498214 s**. Dependencies and Docker layers were
cached; these are explicitly later reproducible baseline measurements, not a
reconstruction of the original uncaptured build total or cold-install times.

The initial sandbox Node invocation reported only three passing *files*, not
individual tests. A rerun outside the sandbox verified 79 individual tests. The
initial sandbox Python run stalled; the verified runs above allowed local socket
access. Dependency download and Docker socket access also required sandbox
escalation. These are execution-environment limitations, not successful checks.

## Suite inventory and purpose

Counts below are parametrized cases, not just test functions. There were no
xfails, deselections or intentional skips except the optional DSN skips.

| Suite | Baseline cases | Layer and purpose | Isolation / limitation |
| --- | ---: | --- | --- |
| `tests/test_api.py` | 12 | In-process HTTP integration: demo endpoints, filters, export, typed contract, null/expired projections | FastAPI TestClient, synthetic rows and patched DB failure; no actual server |
| `tests/test_config.py` | 2 | Unit: required DB password, bounded connection timeout | Environment monkeypatch; no credential store |
| `tests/test_ingestion.py` | 50 | Unit: AIS validation, sentinel handling, retries, row isolation, MQTT lifecycle | TransactionConnection models aborted SQL, fake Paho client and clock; no broker |
| `tests/test_predictions.py` | 21 | Unit: constant-course geometry, invalid motion, row isolation and scheduler failure | Reuses TransactionConnection; no real scheduler or learned model |
| `tests/test_launcher.py` | 2 | Process smoke: reject missing configuration and malformed port | Subprocess Bash; no successful live launch |
| `tests/test_postgres.py` | 3 | Database integration: ingestion, prediction upserts and API retrieval | Real PostgreSQL with simplified temporary DDL, patched service connections; **not `schema.sql`** |
| `research/test_evaluate.py` | 9 | Synthetic scientific code validation: straight/turning tracks, sentinel exclusion, deduplication, attribution | `make_synthetic` and evaluator share planar assumptions; no real-data accuracy validation |
| `research/test_download_d1.py` | 17 | Unit/file integration: paging, two-copy verification, gzip/count checks, provenance, traversal/token safety, late writes, index plan | Fake Cloudflare HTTP, real local gzip/files and SQLite query planning; no D1 service |
| `tests/worker.test.mjs` | 27 | Unit/in-process HTTP: raw validation, projection, deduplication, filters/exports, cache, health and land flags | Mock fetch/cache/assets and fake D1; Node, not workerd |
| `tests/collector.test.mjs` | 18 | Unit: raw gzip archive, UTC keys, idempotency, retention/caps, metadata and scheduled dispatch/failure | Real Node CompressionStream but fake D1/HTTP; no Cloudflare scheduler |
| `tests/frontend.test.cjs` | 34 | Frontend logic unit: server-only projections, expiry/removal, caps/counts, filtering, popup escaping, disclaimer | Extracted inline script in VM; manufactured DOM and Leaflet, no browser |

`tests/conftest.py` forces demo mode, a test-only password and temporary logs
before service imports. Node fixtures are constructed inline; Worker fetch and
cache are restored after tests. `tests/fake_d1.mjs` recognizes the exact SQL
strings used by the implementation and models only those operations. The
748-vessel snapshot in `scripts/baseline/` is an audit input, **not an independent
projection golden**. At the baseline no versioned raw-AIS/golden pair existed;
the independently calculated pair added afterward is described above.

## Tests that can preserve incorrect assumptions

- Worker and Python coordinate constants pin the planar implementation without
  documenting an independent calculation or reviewed oracle.
- Fake D1 accepts precisely the SQL the Worker emits; a passing fake cannot
  establish that SQLite/D1 accepts the statement or enforces the real migration.
  Exact SQL/index assertions protect query cost but are implementation checks.
- Frontend `getElementById` creates missing elements. The harness removes real
  map initialization and manually supplies valid metadata. Notice removal,
  broken Leaflet loading and actual layout can pass these tests.
- Synthetic research generation and evaluation share motion assumptions.
  Excluding sentinel speeds verifies today's scoring rule but does not prove
  abstentions are counted. Existing sample counts include a target 60 seconds
  early; no independently locked tolerance boundary protects that rule yet.
- API list/detail/export agreement establishes consistency, not independent
  correctness of the shared formatter.

Keep these useful regression tests; add independent validation at the boundary
rather than replacing them with more mocks.

## Critical paths missing at the baseline

These were baseline gaps, not the current state. The focused suite documents
linked above record their implemented software checks and remaining evidence
limits. Source-dependent regeneration, production operation, main enforcement
and locked real-data evaluation remain unverified:

1. Independently calculated, versioned golden output through the raw AIS HTTP
   pipeline, covering every projection and coastline null field; deliberate
   invalid-speed, horizon, land-warning and fabricated-projection mutations.
2. Real Chromium/DOM/Leaflet tests with deterministic API and offline tiles:
   projection deletion/expiry, 600/1,000 responses, disclosure, failures/retry,
   filters, popup escaping, marker visibility and mobile controls.
3. workerd entrypoint and local D1 migration, actual compressed writes, cron
   failures, retention, health and API/export responses. No production bindings.
4. Real PostgreSQL `schema.sql` compatibility and Docker demo startup/HTTP smoke.
   Avoid substantial investment in the legacy stack scheduled for removal (#26).
5. Land-mask checksum/header/bounds and source-available deterministic build;
   measured bundle budget. The baseline dry run had no explicit size gate; the implemented budget is
   614400 gzip bytes.
6. Coverage for production modules, measured regression policy and targeted
   mutation evidence. The baseline CI did not measure coverage or mutation survival; final CI
   measures coverage and targeted mutation detection.
7. Research split independence, purge gaps, tolerance edges, metre reference
   distances, counted abstentions and vessel-dependent confidence intervals
   under #16–#18. Actual accuracy evaluation needs locked independent archived
   data outside ordinary PR CI. Software passes permit no accuracy claim.

## Delivery and enforcement

Issue #12 already has golden, asset, budget and contributor requirements. NumPy
is pinned and research tests already execute; do not duplicate that completed
work. Deliver in the requested order: baseline/hygiene; independent goldens;
browser E2E; Workers/D1; enforcement/infrastructure; coverage/mutations. Research
is a separate workstream. PR #38 is merged; its branch remains untouched.

The baseline PR establishes `python-tests`, `node-tests`, and `build-checks`.
The final workflow also includes passing `worker-runtime` and `browser-e2e`
jobs, consolidating the temporarily separate focused workflows.
Configure required checks/PR review on main **after** all final job names are
established and stable; requiring nonexistent checks can block all merging.
Do not merge an implementation PR before CI passes, and keep production
deployment approval manual. Job timeouts currently bound hangs to 10 minutes
for test jobs and 15 minutes for builds; they are operational limits, not measured
performance regression budgets. Record actual GitHub job durations after CI.

PR #39 CI run `38571765554` verified Python 3.11: **123 passed in 1.74 s**,
zero skips/deselections. Node executed 79 cases with zero skips. Whole-job times
were Python 35 s, Node 10 s, builds 33 s (including setup and uploads). All three
jobs passed; this establishes a first measurement, not a stable timing budget.
