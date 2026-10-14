# Workers runtime tests

Run `npm ci --ignore-scripts` then `npm run test:runtime` with Node 22.
`@cloudflare/vitest-plugin` 1.4.2 and Vitest 5.0.4 execute these tests inside
local workerd, reading the repository's Wrangler entrypoint/configuration. D1
is overridden with a local test-only database and the real migrations are
applied before each case. Storage is reset after each test; no remote bindings,
production credentials or external upstream requests are needed. Global fetch
is replaced in every test, including unexpected destinations.

The suite covers the actual entrypoint's metadata, list/detail/export contract,
invalid queries, cache and upstream failures. Cron tests cover minute/daily
dispatch, real D1 writes and constraints, compressed contents, raw sentinels,
idempotency, retention rejection, empty/stale/fresh health, missing tables and
real write rejection. Existing Node unit tests remain unchanged. Assets are
not exposed by the plugin's entrypoint helper; browser tests must serve actual
assets separately.

Vitest's host filesystem transform cache is disabled because workerd cannot
read those paths. The initial default-cache run failed before collecting any
tests; disabling it allowed 11 initial cases to run in 1.69 seconds. The final
suite adds a real write-rejection regression. JUnit results are uploaded and
checked for empty/skipped/failing execution. The focused #40 branch used separate `runtime.yml`; the combined #47
workflow consolidates `worker-runtime` into `ci.yml`. The guard script is identical to #39's.

Clean-install final local result: **12 passed, zero skips, 1.78 s**; existing
Node suites: **79 passed, zero skips, 191.21 ms**, Node 22.23.1. No production
code was changed. A database trigger that aborts INSERT demonstrates that
write failure is observed by the scheduled handler, rather than just modeled
by a fake service. Real Cloudflare network scheduling remains unverified.

Reference: [Cloudflare Vitest integration](https://developers.cloudflare.com/workers/testing/vitest-integration/)
and [test APIs](https://developers.cloudflare.com/workers/testing/vitest-integration/test-apis/).
