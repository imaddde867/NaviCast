# Prediction evaluation data

The hosted Worker's public API is stateless and serves no vessel history. This branch contains an undeployed D1 archive collector and an experimental offline evaluator. No archive continuity or forecasting accuracy has been established.

## Archive prototype

Storage design: Cloudflare D1 (Workers Free), one table, `archive_objects`, created by `migrations/0001_archive_objects.sql`. R2 is not used. Each row is one gzipped object: `key` (primary key), `kind` (`ais` or `meta`), `scheduled_at` and `fetched_at` (epoch ms), `data_updated_at`, `count` and `body` (BLOB). The Worker binds the database as `AIS_ARCHIVE_DB`.

- `ais/YYYY/MM/DD/HH/mm.ndjson.gz`: one row per scheduled UTC minute (cron `* * * * *`), from `event.scheduledTime`, so a delayed invocation does not move its data into the following minute. The body is gzip NDJSON. Its header contains `schema`, `fetched_at`, `source`, `count` and `data_updated_at`; vessel rows contain `mmsi`, `lat`, `lon`, `timestampExternal`, `age_s`, `sog`, `cog`, `heading`, `rot`, `navStat`, `posAcc` and `raim`. Raw motion sentinels and stale observations are retained for offline filtering. Invalid vessel identifiers and positions are excluded.
- `meta/YYYY/MM/DD.json.gz`: one row per UTC day (cron `10 0 * * *`) from `https://meri.digitraffic.fi/api/ais/v1/vessels`. The body is gzip of one JSON object `{schema, source, fetched_at, data_updated_at, count, vessels}`. Vessel entries carry the feed's static fields (name, call sign, IMO, ship type, destination, draught, ETA) and have no position. Only the MMSI is validated.

Both collectors reuse the Worker's upstream loader (8 s timeout, 2 MiB response cap, manual redirects). Writes use `INSERT ... ON CONFLICT(key) DO NOTHING`, so a retry of the same minute or day is a no-op and the first row is kept. Empty or malformed feeds, bodies over 1,900,000 bytes (D1's row limit is 2,000,000 bytes), a missing binding and D1 errors throw. The scheduled handler awaits the collector, so a failure marks the cron run failed in Cloudflare rather than being hidden by `waitUntil`.

Capacity guard: before fetching, the collector runs `SELECT 1` and reads `meta.size_after`. At or above 350,000,000 bytes (`PAUSE_AT_BYTES`) it throws `archive paused: storage threshold` and writes nothing. If D1 reports no size it also pauses, with a different message. That D1 returns `size_after` for read queries is taken from the example on the [D1 return object](https://developers.cloudflare.com/d1/worker-api/return-object/) page; it has not been tested against a live database. The Workers Free per-database limit is 500 MB per the [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) page.

`GET /health` returns `{ok: true, age_s}` (200) when the newest `ais/` row was fetched within five minutes, otherwise 503 (`{ok: false, age_s}` when stale, `{ok: false}` when there are no rows or D1 fails). It reads one row through the primary-key index (`key >= 'ais/' AND key < 'ais0' ORDER BY key DESC LIMIT 1`; D1 `rows_read` for it has not been measured) and is not cached.

Source: [Fintraffic / digitraffic.fi](https://www.digitraffic.fi/en/marine-traffic/), license [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Archive rows select upstream fields and add observation age; evaluation outputs also carry attribution. Raw archive files and metadata contain real MMSIs and must remain private and uncommitted. The proposed removal process in issue #7 remains an owner decision; publication of a contact address does not implement exclusion or deletion.

## Retention plan and capacity

D1 Free cannot hold the archive indefinitely, so D1 is a short buffer, not the archive of record:

1. Weekly, the owner runs `scripts/archive/download_d1.py` for each closed UTC day. It is read-only: it pages through the Cloudflare D1 query API with `CLOUDFLARE_API_TOKEN`, validates every object (key, scheduled time, header, counts, MMSI), writes two independent local copies and a SHA-256 manifest, and reports missing minutes and repeated `data_updated_at`.
2. Only after both copies and the manifest verify does the owner decide, per day, whether to delete that day's rows from D1. Nothing in the Worker or the downloader deletes rows; deletion is a manual, owner-approved step.

Measured sizing: the local probe `scripts/baseline/collector_cpu.mjs` compressed one real 960-record snapshot to 29,807 bytes (one fixture, one time of day). At roughly 30 KB per minute that is about 43 MB per day, so the 350 MB guard is reached after roughly 8 days of collection. This is body bytes only; SQLite and index overhead are not included, and the daily metadata object size is not measured. Hence the weekly cadence is the upper bound, and a missed week pauses archiving rather than losing data silently.

Each invocation issues two D1 statements (the size check and the insert); the Free limit is 50 queries per invocation. Rows written per day against the 100,000 Free limit have not been measured, and indexed writes count extra per the pricing page, so check the D1 metrics after the owner deploys.

## Status and deployment gate

Nothing is deployed and no cloud resource has been created. The `database_id` in `wrangler.jsonc` is a placeholder. The owner has not yet confirmed that the account is on Workers Free, and R2 activation was excluded because its checkout requires a payment method.

CPU: the 4.5 ms p95 printed by the local probe (Node on a development machine, fake in-memory D1, 50 warm samples) is not Workers CPU time. It says nothing about the Workers Free CPU limit, and the daily metadata invocation has not been probed at all.

Owner steps before the archive can start, none of which this branch performs:

- Confirm the account is on Workers Free, create the D1 database, replace the placeholder `database_id`, and apply `migrations/0001_archive_objects.sql`.
- Run `npm ci`, `npm test` and `npm run check:deploy`; a dry-run validates the bundle, not that the database exists or free-tier CPU compliance.
- Deploy, then confirm that `/health` is 200, that minute rows decompress correctly with scheduled-time keys, that `size_after` is reported (otherwise the guard pauses archiving), and that the first daily metadata row appears.
- Measure deployed CPU for both crons, and verify failure alerting and archive continuity before declaring #9 complete.

## Experimental evaluation

```bash
python -m pip install -r research/requirements.txt
python research/make_synthetic.py /tmp/ais-demo
python research/evaluate.py /tmp/ais-demo --json /tmp/navicast-evaluation.json
python -m pytest research -q
```

Observations are deduplicated by vessel identifier and source timestamp. Only valid motion records are scored. Source observation time, not collection time, drives matching. Persistence and dead reckoning are evaluated on the same matched rows, overall and by speed bucket; errors are reported in metres. No training split is implemented.

The evaluator remains a prototype: the current fixed truth-matching tolerance, projection over matched elapsed time, whole-archive memory use and lack of vessel-level confidence intervals do not satisfy the protocol and streaming requirements in [#16](https://github.com/imaddde867/NaviCast/issues/16), [#17](https://github.com/imaddde867/NaviCast/issues/17) and [#18](https://github.com/imaddde867/NaviCast/issues/18). Do not publish its results as validated accuracy claims. Do not split AIS rows randomly or use held-out target positions in prediction code. Scientific-method changes require a reviewed protocol before implementation.

The feed's location endpoint does not contain ship type. Daily vessel metadata is collected by the undeployed `meta/` cron described above; joining that metadata into serving and evaluation is tracked separately in #14. Sparse tracks and repeated upstream snapshots reduce usable evaluation coverage. A continuity check must treat a missing object, an empty snapshot or repeated `data_updated_at` as a gap.
