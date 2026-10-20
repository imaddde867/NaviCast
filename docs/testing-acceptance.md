# Hardening acceptance audit — 2026-10-14

This audit records completed software/CI hardening and observed repository
enforcement. It distinguishes these results from unperformed physical
coastline regeneration and real-data forecasting validation.
PR #38 is merged at `dca965c`; its branch was untouched. Focused implementation
PRs #39–#42 and #44–#47 are all merged; none was replaced by an aggregate PR.

The combined five-job workflow passed on `82c483f` and documentation-only
`8acf0d4`: [GitHub run 38604336253](https://github.com/imaddde867/NaviCast/actions/runs/38604336253).
Its reports are stronger evidence than a green badge alone: full per-case
inventories, zero skips/deselections, real local services, actual browser layers,
independent references and executed-assertion mutation failures.

| Requirement | Evidence and scope | Status |
| --- | --- | --- |
| Reproducible baseline; every original suite/fixture/mock/workflow audited and classified | `docs/testing.md` records original 116 Python/79 Node cases, optional skips, timings, unit/integration/scientific/VM limits, reproducible commands and original build checks | Verified; initial Docker total was absent, so later unchanged-main cached build/configuration rerun timings are separately recorded |
| Independent complete projection oracle | Synthetic raw AIS plus 23 full accepted rows in `tests/fixtures/` and `tests/golden/`; independently recalculated selection, coordinates, times, nulls and raster classifications; list/detail/export/cache tests | Verified and independently reviewed; owner-authorized #41 merge |
| Four specified projection defects turn tests red | Temporary-copy mutation script requires all three baseline golden tests to execute and detects invalid speed, horizon change, land-flag suppression and fabricated null projection | Verified locally and CI, 4/4 |
| Real browser scenarios and DOM/map rendering | Twelve Chromium cases at audit time serve actual dashboard/Leaflet, deterministic API/tiles; assertions inspect real attached layers/pixels, user-visible notices, limits/counts, null/removed forecasts, retries, filtering, popups and mobile controls | Verified on #42/integration; icon-font rendering excluded, overlapping-marker center-click UX excluded at audit time (#43, fix in #52) |
| Browser notice/fallback/request-limit defects turn tests red | Temporary real-browser copies with actual markup/script mutations; baseline executes two targeted cases | Verified locally and CI, 3/3 |
| Actual Cloudflare runtime and isolated D1 | Twelve workerd cases use repository Wrangler entrypoint, real migration and local binding; real gzip/row/constraint/cron/retention/health/error/idempotency assertions | Verified on #40/integration; production scheduling not exercised |
| API responses end to end | Runtime entrypoint list/detail/JSON and CSV exports, invalid queries, upstream errors/cache; independent full projection JSON oracle and real browser request-limit assertions | Verified for deterministic local runtime/browser contracts |
| Five stable CI jobs; versions, reports, secrets, permissions | Exactly python-tests/node-tests/worker-runtime/browser-e2e/build-checks; Python3.11/Node22, pinned installs, inventories and coverage gates, always-upload reports/traces, explicit Bash pipefail, read-only permissions | Verified on merged main61c1825, run38617255513 |
| Critical tests cannot silently skip or run as subsets | JUnit guards reject skips/failures/errors/empty/missing required testcase identities; pytest required mode rejects deselection; ten guard/coverage regression tests independently rerun | Verified for all four combined suites (142/83/12/12) |
| Required PRs/checks and no ordinary bypass on main | `.github/main-protection.json` matches five jobs, mandatory PRs and administrator enforcement; owner-approved zero review-count gate for the verified sole collaborator; live REST verification binds all five checks to Actions app15368 | **Verified active on main after its green five-job run** |
| Deliberately failing critical PR blocks merging | Local/CI mutations prove assertion sensitivity; repository merge policy probe requires active protection | **Verified: non-draft/current/clean #48 BLOCKED, only node-tests failed; probe closed unmerged** |
| Measured coverage and regression policy | Python statement/branch, Node V8 line/branch and actual inline-dashboard Chromium converted coverage; maximum uncovered counts per production module; `docs/testing-quality.md` | Verified; V8 branches are not AST branch coverage |
| Targeted mutation measurement | Four projection, three browser, three scientific campaigns require passing baselines and assertion failures; infrastructure negative controls separately recorded | Verified; no broad automated mutation tool or total-score claim |
| Actual schema compatibility without overinvesting in legacy stack | Four disposable PostgreSQL cases apply `schema.sql`, exercise ingestion/prediction/API and constraints, remove only their own schemas | Verified locally and Python3.11 CI |
| Docker operates, not merely builds | Real demo container responds to dashboard/meta/health/list/detail/JSON/CSV; broken startup negative control fails | Verified locally and CI; no production database/network needed |
| Geographic integrity and bundle budget | Asset byte checksum/header/bounds/canonical encoding/decoded fraction;574527gzip bytes under614400budget; changed bytes/excess budget fail controls | Verified locally and CI |
| Deterministic geographic regeneration when inputs available | Executable two-build/full-field comparison excluding built_at in `check_land_regeneration.py` | Conditional input absent: original source ZIP unavailable; no regeneration claim |
| Synthetic scientific independence, purge, matching, metres, abstentions, dependence and scoring-rule drift | Fifteen new tests and separate split/bootstrap helpers; versioned prototype descriptor; independent geometric and five-vessel interval references; row-bootstrap/purge/tolerance mutations detected | Verified software code, not a locked forecasting protocol |
| Independent forecasting-quality evaluation outside PR CI | #16–#18 retain locked dates/margin/tolerance/streaming/adoption decisions; #19 owns archived pilot data evaluation | Not run; no forecasting accuracy claim permitted |
| Focused PR delivery and unresolved findings | Eight PRs committed/pushed with green checks and requested first-person work reports; #12 progress updated, #16–#18 bounded updates, #43 fix in open #52 | Verified; reviewed focused merges complete |
| Second-brain current status reconciled | Canonical portfolio note, archived pointer, provenance and recent digest committed/pushed; vault checker zero structural errors | Verified; existing CONTEXT size warning retained without deleting knowledge |
| No automatic production deployment | Workflow contains local tests/builds and Wrangler deploy --dry-run only; no production secrets/resources/deployment used | Verified within this implementation scope |

Completed rollout and actual API/merge-blocking evidence are recorded in
[testing-enforcement.md](testing-enforcement.md). The negative probe was closed
unmerged and its remote branch deleted. Original source regeneration remains
conditional on unavailable inputs; forecasting-quality evaluation remains a
separate locked-protocol workstream, with no accuracy claim.
