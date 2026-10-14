# AIS archive runbook (D1)

Operating procedure for the per-minute AIS archive. For design and measurements see [evaluation.md](evaluation.md) and [hosting.md](hosting.md). Tracking issue: #35.

Fixed facts:

| Item | Value |
|---|---|
| Account id | `a9b21695a21bf07980d486637f1a5a6e` |
| D1 database | `navicast-ais-archive`, id `cb69e58b-d90d-4e83-ab1b-fcae470de050` |
| Live Worker | `navicast`, `https://navicast.imadlab.com` |
| Archive started | 2026-10-13 18:08 UTC (first row `ais/2026/10/13/18/08.ndjson.gz`) |
| Crons | `* * * * *` (AIS snapshot), `10 0 * * *` (vessel metadata) |
| Pause rule | collector refuses to run when the oldest `ais/` row is more than `MAX_RETENTION_DAYS` (8) days older than the run time |
| Measured | about 33 KB gzip and about 1,050 vessels per minute, about 48 MB/day (evening and night sample, 2026-10-13/14) |

All times UTC unless noted. Helsinki is UTC+3 until 2026-10-25.

## Ground rules

1. **Never paste an API token, or a screenshot showing one, into chat, an issue or a commit.** Use `read -s CLOUDFLARE_API_TOKEN && export CLOUDFLARE_API_TOKEN` in your own shell. The variable exists only in that shell. Give every token a short expiry and revoke it after use.
2. **Never delete archive rows before the downloader has exited 0 for that day and both local copies are verified.** Deletes need the owner's explicit approval each time.
3. **Delete by the explicit key list from the manifest, never by key range.** A delayed invocation can still write a late key into a closed day.
4. **Never download today (UTC).** The downloader refuses a day that is not yet closed.
5. **Keep the archive out of git and out of any public place.** It holds AIS positions with MMSIs. The data-removal policy is not decided yet (#7), so treat it as private.
6. Do not push to `main`, deploy, or create cloud resources without the owner's approval.
7. Missed minutes cannot be backfilled (the upstream feed is live only). A paused collector loses data permanently.

## When to run what

| When (UTC) | Task |
|---|---|
| Any time | Section 1: health check |
| After 00:15 UTC on a given day | Section 2: metadata row for that day exists |
| After 00:05 UTC, for the previous (closed) day | Section 3: closed-day size and CPU check (first time: 2026-10-15) |
| Every 3 to 4 days at first, never more than 6 days apart | Section 4: verified download, then Section 5: cleanup |
| By 2026-10-21 18:08 UTC at the latest | Oldest row must have been cleaned, or the collector pauses |

## 1. Health check (no token)

```
curl -s -w '\nhttp=%{http_code}\n' https://navicast.imadlab.com/health
```

- `200` with `{"ok":true,"age_s":N}` and N under about 120: collecting.
- `503` with `{"ok":false,...}`: no archived minute in the last 5 minutes, or the upstream data time is more than 10 minutes old, or D1 failed. Look at cron past events (dashboard, navicast, Settings, Triggers) for the error text. `archive paused: retention exceeded` means cleanup is overdue (Section 5). Right after a deploy it can take up to 15 minutes before cron fires.

## 2. Metadata row (D1 console, no token)

Dashboard, Storage and Databases, D1, `navicast-ais-archive`, Console. **Run one statement at a time** (the console only shows the first result of a multi-statement paste):

```sql
SELECT key, count, length(body) AS bytes FROM archive_objects WHERE kind = 'meta';
```

Expect one row per UTC day since 2026-10-14, key `meta/YYYY/MM/DD.json.gz`, count about 800 to 900. If the row for a day is missing: read the failed cron run for `10 0 * * *`, check for `Upstream body too large` (the 2 MiB cap) or a pause error.

## 3. Closed-day size and CPU check

Run after 00:05 UTC for the previous day. Example for 2026-10-14 (change the date in all three places; the upper bound is the date followed by `0`, e.g. `ais/2026/10/140`):

```sql
SELECT count(*) AS minutes, sum(length(body)) AS bytes, avg(length(body)) AS avg_body,
       max(length(body)) AS max_body, avg(count) AS avg_vessels, max(count) AS max_vessels
FROM archive_objects
WHERE key >= 'ais/2026/10/14/' AND key < 'ais/2026/10/140';
```

- `minutes` should be 1440. A few missing minutes are normal; many are not. List them with the manifest field `ais_minutes_missing` after Section 4.
- Database file size: dashboard D1 page, or `npx wrangler d1 info navicast-ais-archive` (needs a token).
- **Decision rule:** projected 8-day file size = file size now divided by days since 2026-10-13 18:08 UTC, times 8. If that is above about 420 MB, lower `MAX_RETENTION_DAYS` from 8 to 7 (or 6) in `cloudflare/collector.mjs`, `docs/evaluation.md` and `docs/hosting.md` through a PR, then deploy with the owner's approval. D1 Free allows 500 MB per database.
- **Workers CPU:** dashboard, Workers and Pages, `navicast`, Metrics, last 24 hours. Note CPU time p50 and p99, requests, and errors. The Free limit is 10 ms per invocation. If p99 is above about 8 ms, investigate before relying on the collector; error code 1102 or gaps in `minutes` point at CPU. The local probe numbers (4.5 ms snapshot, 3.5 ms metadata) are Node on a development machine, not Workers CPU.
- Requests per day against the 100k Workers Free limit. Whether cron invocations count towards it is undocumented; note what you see.
- Write the numbers as a comment on #35 and update the "about 43 MB/day" figures in the docs if they changed.

## 4. Verified download

Needs a Cloudflare API token with Account, D1, Read, expiry end of day. Whether Read is sufficient for queries through the API is unverified; if the script reports an authentication error, use a token with D1 Edit and the same short expiry. The script only runs `SELECT`.

```
cd ~/GitHub/experiments/navicast        # any checkout of main; stdlib Python only
read -s CLOUDFLARE_API_TOKEN && export CLOUDFLARE_API_TOKEN

python3 scripts/archive/download_d1.py \
  --account-id a9b21695a21bf07980d486637f1a5a6e \
  --database-id cb69e58b-d90d-4e83-ab1b-fcae470de050 \
  --day 2026-10-14 \
  --output-dir ~/navicast-archive/primary \
  --backup-dir <second independent location>
```

- The two directories must be independent roots, neither inside the other. Put the second on a different disk or machine if you can (mounted external disk, or another host synced afterwards). The output is **outside** the repository.
- One command per closed day, oldest first. 2026-10-13 is a partial day (starts 18:08 UTC) and downloads the same way; its missing minutes will be listed.
- It writes `ais/YYYY/MM/DD/HH/mm.ndjson.gz`, `meta/YYYY/MM/DD.json.gz` and `manifest-YYYY-MM-DD.json` into both roots, re-reads and SHA-256 checks both copies, and cross-checks row count and bytes against the server before writing the manifest.
- Success prints one JSON line (`files`, `ais_minutes_present`, `ais_minutes_missing`, `meta_present`, `repeated_data_updated_at`) and exits 0. Check: `files` equals `ais_minutes_present` plus 1 (the metadata row) and `meta_present` is true.
- If a page fails near the size cap, rerun with `--page-size 1`.

Independent check of the two copies:

```
diff -rq ~/navicast-archive/primary <second independent location> && echo copies identical
```

| Failure | Meaning | Action |
|---|---|---|
| `day must be a closed UTC day before today` | too early | wait until after 00:05 UTC |
| `no archive rows found for the requested UTC day` | nothing archived that day | check Section 1 and cron history |
| server-side cross-check mismatch (no manifest written) | rows changed while downloading, or a short page | rerun the same command |
| `conflicting completed manifest already exists` | a late key appeared after an earlier successful run | keep the old manifest (rename it, e.g. `manifest-DAY.first.json`), rerun, and delete only after the new run exits 0 |
| authentication or permission error | token scope or expiry | see the token note above |

## 5. Cleanup (owner approval required, each day)

Only for days where Section 4 exited 0 **and** the `diff -rq` check passed. The owner approves each deletion explicitly. Deleting needs a token with Account, D1, **Edit** (create it just for this step, expiry end of day, revoke after).

1. Generate the delete statements from the manifest (100 keys per statement, keys pattern-checked):

   ```
   python3 -I - ~/navicast-archive/primary/manifest-2026-10-14.json delete-2026-10-14.sql <<'EOF'
   import json, re, sys
   keys = [f["key"] for f in json.load(open(sys.argv[1]))["files"]]
   ok = re.compile(r"(ais/\d{4}/\d{2}/\d{2}/\d{2}/\d{2}\.ndjson\.gz|meta/\d{4}/\d{2}/\d{2}\.json\.gz)\Z")
   assert keys and all(ok.fullmatch(k) for k in keys), "unexpected key"
   with open(sys.argv[2], "w") as out:
       for i in range(0, len(keys), 100):
           out.write("DELETE FROM archive_objects WHERE key IN (%s);\n" % ",".join("'%s'" % k for k in keys[i:i + 100]))
   print(len(keys), "keys")
   EOF
   ```

   Read the `.sql` file before running it. It must contain only `DELETE FROM archive_objects WHERE key IN (...)` lines for that day.

2. Execute it against the remote database from a checkout with `node_modules` (`npm ci --ignore-scripts`), after the owner has approved:

   ```
   npx wrangler d1 execute navicast-ais-archive --remote --file delete-2026-10-14.sql
   ```

3. Verify (console, one statement at a time):

   ```sql
   SELECT count(*) FROM archive_objects WHERE key >= 'ais/2026/10/14/' AND key < 'ais/2026/10/140';
   ```
   expects 0, and

   ```sql
   SELECT key FROM archive_objects WHERE key >= 'ais/' AND key < 'ais0' ORDER BY key LIMIT 1;
   ```
   shows the new oldest AIS key. Then run Section 1; `/health` must be 200 and the newest minute current.

4. Record the day, row count and what you observed on #35. Unverified until observed: whether the D1 file size shrinks after DELETE (the pause rule uses row age, so it does not depend on this), and whether DELETE works on a nearly full database.

5. Revoke the tokens.

## If the collector is paused

`/health` is 503 and the cron error is `archive paused: retention exceeded, download and clean up`. Download and verify the oldest days (Section 4), delete them with approval (Section 5). Collection resumes by itself on the next minute. The minutes in between are lost.

## Handing this to an agent

Give the agent this file and #35, name exactly one section, and state the limits:

> Read `docs/archive-runbook.md` and issue #35. Do Section N only. You may run read-only commands and the downloader. Do not delete rows, deploy, create resources, merge, or push to main. Never print or store the API token; I export it in my own shell. Report exact outputs and anything you could not verify.

Cleanup (Section 5) is always run by the owner or explicitly approved step by step.
