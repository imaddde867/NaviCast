# Prediction evaluation data

The hosted Worker's public API is stateless and serves no vessel history. This branch contains an undeployed D1 archive collector and an experimental offline evaluator. No archive continuity or forecasting accuracy has been established.

## Archive prototype

Storage design: Cloudflare D1 (Workers Free), one table, `archive_objects`, created by `migrations/0001_archive_objects.sql`. R2 is not used. Each row is one gzipped object: `key` (primary key), `kind` (`ais` or `meta`), `scheduled_at` and `fetched_at` (epoch ms), `data_updated_at`, `count` and `body` (BLOB). The Worker binds the database as `AIS_ARCHIVE_DB`.

- `ais/YYYY/MM/DD/HH/mm.ndjson.gz`: one row per scheduled UTC minute (cron `* * * * *`), from `event.scheduledTime`, so a delayed invocation does not move its data into the following minute. The body is gzip NDJSON. Its header contains `schema`, `fetched_at`, `source`, `count` and `data_updated_at`; vessel rows contain `mmsi`, `lat`, `lon`, `timestampExternal` (only integers are kept, otherwise null), `age_s`, `sog`, `cog`, `heading`, `rot`, `navStat`, `posAcc` and `raim`. Raw motion sentinels and stale observations are retained for offline filtering. Invalid vessel identifiers and positions are excluded.
- `meta/YYYY/MM/DD.json.gz`: one row per UTC day (cron `10 0 * * *`) from `https://meri.digitraffic.fi/api/ais/v1/vessels`. The body is gzip of one JSON object `{schema, source, fetched_at, data_updated_at, count, vessels}`. Vessel entries carry the feed's static fields (name, call sign, IMO, ship type, destination, draught, ETA) and have no position. Only the MMSI is validated.

Both collectors reuse the Worker's upstream loader (8 s timeout, 2 MiB response cap, manual redirects). Writes use `INSERT ... ON CONFLICT(key) DO NOTHING`, so a retry of the same minute or day is a no-op and the first row is kept. Empty or malformed feeds, bodies over 900,000 bytes (D1's row and string limit is 2,000,000 bytes, and the downloader reads `hex(body)`, which doubles the size on the wire), a missing binding and D1 errors throw. The scheduled handler awaits the collector, so a failure marks the cron run failed in Cloudflare rather than being hidden by `waitUntil`.

Retention guard: before fetching, the collector reads one row through the primary-key index (`SELECT key FROM archive_objects WHERE key >= 'ais/' AND key < 'ais0' ORDER BY key LIMIT 1`). If the oldest AIS key is more than `MAX_RETENTION_DAYS` (8) older than the scheduled time it throws `archive paused: retention exceeded, download and clean up` and writes nothing; the metadata cron applies the same check. The guard uses age rather than database size because SQLite may not shrink the database file after `DELETE` (freed pages stay on a freelist), so a size-based pause might never lift; whether D1 reports a smaller `size_after` after deletes was not tested against a live database. Eight days is the sizing below (about 345 MB) against the Workers Free per-database limit of 500 MB on the [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) page. Collection resumes on its own once the old days are deleted. `data_updated_at` is stored as a string or null identically in the header and the row.

`GET /health` returns `{ok: true, age_s}` (200) when the newest `ais/` row was fetched within five minutes, otherwise 503 (`{ok: false, age_s}` when stale, `{ok: false}` when there are no rows or D1 fails). It also returns 503 `{ok: false, age_s}` when the newest row's `data_updated_at` parses as a date more than ten minutes old (the upstream froze while the collector kept fetching); a null or unparseable value alone does not fail the check. It reads one row through the primary-key index (`key >= 'ais/' AND key < 'ais0' ORDER BY key DESC LIMIT 1`; D1 `rows_read` for it has not been measured) and is not cached.

Source: [Fintraffic / digitraffic.fi](https://www.digitraffic.fi/en/marine-traffic/), license [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Archive rows select upstream fields and add observation age; evaluation outputs also carry attribution. Raw archive files and metadata contain real MMSIs and must remain private and uncommitted. The proposed removal process in issue #7 remains an owner decision; publication of a contact address does not implement exclusion or deletion.

## Retention plan and capacity

D1 Free cannot hold the archive indefinitely, so D1 is a short buffer, not the archive of record:

1. Weekly, the owner runs `scripts/archive/download_d1.py` for each closed UTC day. It is read-only and has no delete capability. It pages the day's AIS keys with a primary-key range query (10 rows per page, no `OR` and no `kind` predicate; the test suite runs the real SQL against SQLite and asserts index-only plans), fetches the `meta/` row by key, validates every object (key, scheduled time, header, counts, MMSI), writes two independent local copies, and before any manifest compares the downloaded AIS count and total bytes, and the metadata row, with server-side `count(*)`/`sum(length(body))`. A mismatch (for example a late write from a delayed invocation) exits non-zero and writes no manifest; rerun the day. Gaps are not failures: `ais_minutes_missing` and `meta_present` are reported in the manifest and in the one-line summary, with repeated `data_updated_at` values.
2. Only when the script exited 0 for a day and both copies verify may the owner decide to delete that day's rows from D1. Nothing in the Worker or the downloader deletes rows. The deletion procedure is in [hosting.md](hosting.md).

Measured sizing: the local probe `scripts/baseline/collector_cpu.mjs` compressed one real 960-record snapshot to 29,860 bytes and one real 848-vessel metadata response to 39,764 bytes (one fixture each, one time of day). At roughly 30 KB per minute that is about 43 MB per day, so eight days is about 345 MB. This is body bytes only; SQLite and index overhead are not included. Hence the weekly cadence is the upper bound, and a missed week pauses archiving after day eight rather than losing data silently.

Each invocation issues two D1 statements (the retention check and the insert); the Free limit is 50 queries per invocation. Rows written per day against the 100,000 Free limit have not been measured, and indexed writes count extra per the pricing page, so check the D1 metrics after the owner deploys.

## Status and deployment gate

Nothing is deployed and no cloud resource has been created. The `database_id` in `wrangler.jsonc` is a placeholder. The owner has not yet confirmed that the account is on Workers Free, and R2 activation was excluded because its checkout requires a payment method.

CPU: the local probe prints a p95 of 4.5 ms process CPU for the snapshot collector and 3.5 ms for the metadata collector (Node on a development machine, fake in-memory D1, 50 warm samples each). These are not Workers CPU time and say nothing about the Workers Free CPU limit.

Owner steps before the archive can start, none of which this branch performs:

- Confirm the account is on Workers Free, create the D1 database, replace the placeholder `database_id`, and apply `migrations/0001_archive_objects.sql`.
- Run `npm ci`, `npm test` and `npm run check:deploy`; a dry-run validates the bundle, not that the database exists or free-tier CPU compliance.
- Deploy, then confirm that `/health` is 200, that minute rows decompress correctly with scheduled-time keys, and that the first daily metadata row appears.
- After the first full UTC day, compare the measured D1 size and bytes per day with the ~43 MB/day estimate (from one 960-vessel snapshot; busier periods may differ). If it is higher, lower `MAX_RETENTION_DAYS` before the 8-day window can approach the 500 MB database limit. A full D1 fails inserts closed (`/health` goes 503) but whether DELETE still works on a full database is unverified.
- If a download page ever fails near the body cap, retry with `--page-size 1`; whether the D1 REST API accepts 10 x ~1.8 MB hex responses is untested.
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
