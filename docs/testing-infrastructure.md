# Infrastructure and geographic artifacts

`tests/test_postgres.py` now applies the actual `schema.sql` to a uniquely named
schema inside a disposable database instead of defining simplified temporary
tables. Every test drops only its own schema. The suite verifies ingestion,
prediction persistence and retrieval, duplicate/null constraints and safe schema
reapplication (including the real cleanup function). It uses the existing
`NAVICAST_TEST_DSN`; do not point it at production. This is an essential legacy
compatibility check, not a new investment in the stack scheduled for removal
in #26.

After `docker build -t navicast-check .`, run `bash scripts/check_docker.sh`.
It starts demo mode on a Docker-assigned loopback port, waits for startup,
checks the actual dashboard, `/meta`, `/health`, list/detail and both exports,
then removes its own container even on failure. No database or live MQTT feed
is needed. HTTP assertions are part of the smoke script; a built image alone
cannot satisfy this check.

`npm test` includes land-mask byte integrity, header, bounds, canonical base64,
row encoding and reconstructed land-fraction checks. The committed SHA-256 is
`9154aea90f28a1ec87f017335a44fe48cf736910a1ec1abf513ef3cba6ac7f41`.
Refreshing the asset requires reviewing the source snapshot, metadata and new
checksum together; silently changing the expected checksum is not validation.

`npm run check:bundle` performs a Wrangler dry run to a temporary output
directory and sums gzip sizes of emitted JS/Wasm modules. The baseline dry run
was 561.06 KiB gzip; the budget is **600 KiB (614400 bytes)**, leaving about
39 KiB for reviewed growth before a budget discussion. Static assets are served
separately and do not count toward the Worker code budget. Nothing is deployed.

## Source-available regeneration

The 0.9 GB OSM source ZIP is not committed or present in this workspace. CI
therefore checks committed integrity rather than claiming to rebuild it. With
the reviewed source snapshot available, install the build-only dependency
versions documented in `scripts/build_land_mask.py`, then run:

```sh
python scripts/check_land_regeneration.py /explicit/path/to/land-polygons-split-4326.zip
```

It rebuilds twice, compares all header/data fields except `built_at`, and checks
against the committed asset. It fails for a different source snapshot. This
source-dependent check remains unexecuted until that exact input is supplied;
the integrity test is required and never skipped.

## Verified evidence (2026-10-14)

- Actual-schema integration: 4 passed in 0.35 s; all Python: 117 passed in 0.82 s.
- Node including asset integrity: 80 passed, zero skips, 191.64 ms.
- Emitted Worker modules gzip: 574527 bytes, below 614400 bytes.
- Running Docker demo: all seven HTTP checks passed and its container was removed.
- Negative controls: an appended byte makes the asset test fail; a 1-byte
  budget rejects the bundle; a temporary image with `CMD ["false"]` fails the
  Docker smoke. The negative image was removed. Main image and sources remained
  intact. Startup retry handles connection resets while Uvicorn starts.
- Source-ZIP regeneration remains unexecuted: the exact source is unavailable.
