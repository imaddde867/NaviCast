# Prediction evaluation data

The hosted Worker is stateless, so it cannot say how accurate its projections are. A Cron Trigger (`* * * * *`) archives the raw Digitraffic AIS snapshot to R2 once a minute. `research/evaluate.py` joins observations at `t` and `t+h` offline and scores any predictor against what the vessel actually did.

## Object layout

One gzipped NDJSON object per UTC minute: `ais/YYYY/MM/DD/HH/mm.ndjson.gz` in bucket `navicast-ais-archive` (binding `AIS_ARCHIVE`). A retry in the same minute overwrites the same key. Written by `cloudflare/collector.mjs`.

## Schema v1

Line 1 is a header: `{"schema":1,"fetched_at":ISO,"source":URL,"count":N,"data_updated_at":ISO}`. Every other line is one vessel with raw upstream values:

`mmsi, lat, lon, timestampExternal (ms), age_s, sog, cog, heading, rot, navStat, posAcc, raim`

Sentinels are kept (`sog` 102.3, `cog` 360, `heading` 511) and stale observations are kept (`age_s` says how old). Filtering is the reader's job. Vessels with an invalid MMSI or position are dropped. An empty or malformed upstream response writes nothing.

## Running the evaluation

```
pip install numpy
python research/make_synthetic.py /tmp/ais-demo          # optional fake data
python research/evaluate.py /tmp/ais-demo --json out.json  # or a dir/glob of downloaded objects
python -m pytest research -q                              # needs pytest too
```

Observations are deduplicated by `(mmsi, timestampExternal)`. For each observation with `0.5 <= sog < 102.3` and `0 <= cog < 360` the nearest later observation within +-60 s of `t+h` (h = 5, 10, 15, 30 min) is the truth. Predictors: `persistence` (last position) and `dead_reckoning` (same formula as the Worker, projected over the real elapsed time). Output is median, p90 and p95 error in metres per horizon, overall and by sog bucket (<2, 2-8, >=8 kn). `--split-by vessel|time` only prints the group assignment a future model split would use; vessel grouping keeps all of a vessel's observations in one fold.

## Limitations

- The REST feed has at most about one position per vessel per minute, and only when the vessel transmits. Sparse tracks reduce `n` at long horizons.
- Ship type is not in `/api/ais/v1/locations`. Type-stratified scoring needs the `/api/ais/v1/vessels` metadata endpoint, joined by MMSI.
- Feed latency makes `fetched_at` later than the true observation time. Use `timestampExternal` for all time arithmetic.
- Size: a live snapshot of 938 vessels was 167 KB as NDJSON and 29 KB gzipped, so about 42 MB per day and 1.3 GB per month (about 43,000 writes per month). Check against current R2 pricing before enabling.
- The free Workers plan limits CPU time per invocation. Parsing, serializing and compressing ~1000 vessels is cheap but should be confirmed in the first runs under Workers observability.
- `evaluate.py` holds all observations in memory. Fine for days of data; shard by date for months.

## Owner steps before first deploy (NOT done)

Nothing below has been run. The bucket does not exist. Create it explicitly first: `npm run check:deploy` is offline and passes without it, but how `wrangler deploy` treats a missing bucket varies by Wrangler version.

1. `npx wrangler r2 bucket create navicast-ais-archive`
2. `npm test && npm run check:deploy`
3. `npm run deploy` (activates the cron trigger as well as the binding)
4. After a few minutes confirm objects appear: `npx wrangler r2 object get navicast-ais-archive/ais/YYYY/MM/DD/HH/mm.ndjson.gz --file out.gz`
5. Optionally add an R2 lifecycle rule to expire objects after N days.
