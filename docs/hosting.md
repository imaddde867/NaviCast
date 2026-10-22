# Hosted live map

NaviCast uses one Cloudflare Worker with static assets at `navicast.imadlab.com`. The Worker adapts the public Digitraffic AIS REST snapshot to the same response fields used by the Python API. It computes constant-course projections from each original observation timestamp and exposes the existing map, filters and JSON/CSV downloads.

A canonical snapshot is cached for 30 seconds per Cloudflare location. The hosted REST feed treats observations older than five minutes as stale; the local MQTT/demo view retains its one-minute threshold. This allows for upstream snapshot latency without replacing source timestamps. Upstream requests use gzip compression and an identifying `Digitraffic-User` header. Invalid or old observations are excluded. An upstream failure returns a visible service error; it never substitutes synthetic data.

GitHub Pages could host the HTML but cannot run the dynamic API or persistent MQTT collector. Supabase could retain history, but would add storage, migrations and access policies that the current public map does not need. The existing imadlab Supabase project is unchanged.

## Maintenance mode and health

[PR #51](https://github.com/imaddde867/NaviCast/pull/51) disabled archive collection on 2026-10-19 after the scheduled snapshot exceeded Workers Free CPU limits. `wrangler.jsonc` keeps `triggers.crons: []`. Existing historical data stays in D1 (`AIS_ARCHIVE_DB`); the live map needs neither archive collection nor D1. No archive history is served by the public Worker. The optional Python/PostgreSQL/MQTT stack remains a local alternative. R2 is not used.

- `GET /health` checks live API availability through the same normalized snapshot and 30-second, per-location cache as `/vessels`. It returns `{ok: true, age_s}` with 200 on success, or `{ok: false}` with 503 on upstream, parsing or cache-path failure. `age_s` is the live snapshot fetch age, not archive or observation age. A valid empty snapshot returns 200; this is availability, not a guarantee of fresh observations or forecasting accuracy. A cached snapshot can mask an upstream outage until its 30-second expiry. Monitor `/health` for public API availability.
- `GET /health/archive` retains the historical D1 freshness diagnostic (five-minute fetch and ten-minute upstream-update thresholds; details in [evaluation](evaluation.md)). A stale archive returning 503 is expected while collection is disabled. Do not use it as live-map readiness or delete data to make it green. Both health responses use `Cache-Control: no-store`; only the underlying live snapshot is cached.

Read-only production verification on 2026-10-22: at 10:09:39 UTC the **pre-patch** `/health` returned HTTP 503 with `{"ok":false,"age_s":242247}`, while `/vessels?limit=1` returned HTTP 200 at 10:09:43 UTC with an AIS observation timestamp of `2026-10-22T10:09:10.450Z`. The Cloudflare schedules API returned `schedules: []`. The latest active deployment was created at `2026-10-19T14:47:03.446074Z`, version `55cc2849-2bd9-4882-88ca-e82727f776cc` at 100% traffic. This verifies disabled production schedules and the health mismatch, not an exact deployed Git commit. The new health semantics still require an owner-run deployment after review.

## Historical retention procedure (inactive)

The following applies only if collection is separately approved and restored after resolving its CPU limit. It is not a maintenance-mode recovery action. Preserve the existing D1 data. Read-only verified downloads remain available; there is no weekly cleanup deadline while no new snapshots are being collected. [Issue #35](https://github.com/imaddde867/NaviCast/issues/35) describes the earlier active-collection plan; its October 21 pause deadline and instructions to restore `/health` via cleanup are historical.

The Worker never deletes archive rows. After the weekly `scripts/archive/download_d1.py` run for a closed UTC day exits 0, and the owner has confirmed both local copies and `manifest-YYYY-MM-DD.json` (including `ais_minutes_missing` and `meta_present`), the owner may delete that day's rows. Delete by the explicit list of `key` values in the manifest's `files`, not by a key range: a delayed invocation could still write a late key into the same day, and a range delete would destroy it unseen. A late key written before you delete makes the next download of that day fail its server-side cross-check; rerun it. If a late key appears after you already deleted that day, the rerun sees only that row and refuses because a different `manifest-YYYY-MM-DD.json` exists: move the old manifest aside (keep it) and rerun, otherwise the row stays and the retention pause cannot lift. Run deletes only with the owner's approval; nothing in this repository performs them. The Worker's `archive paused: retention exceeded` error means the oldest AIS row is more than eight days old; deleting verified days clears it. D1 may not shrink the database file after deletes (unverified on live D1), which is why the guard uses age, not size.

## Release

1. Run Python tests and `npm test`.
2. Run `npm run check:deploy` to validate the Worker bundle and configuration.
3. Review and merge the release PR after CI passes.
4. Only after an explicit owner deployment decision, authenticate with Wrangler and run `npm run deploy`. Keep `triggers.crons` empty; no archive migration or data cleanup is needed for this health change.
5. Verify HTTPS `/health` (live availability), `/health/archive` (expected 503 for stale historical data), `/meta`, `/vessels`, vessel detail and both export formats. Inspect desktop/mobile map rendering and browser console.

Cloudflare provisions DNS and TLS for the Worker custom domain. The configuration names only the NaviCast subdomain. Do not replace the portfolio apex records.

Runtime limits and quotas depend on the Cloudflare account plan. This deployment does not change the plan or introduce paid storage. The 4.5 ms collector figure in the evaluation notes is a local Node probe, not Workers CPU time, and did not establish Workers Free CPU compliance; deployed snapshot collection subsequently exceeded the limit (#51). At high traffic, review request quotas and feed load before increasing refresh frequency.

Sources: [Workers static assets](https://developers.cloudflare.com/workers/static-assets/), [custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/), [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [Digitraffic marine API](https://www.digitraffic.fi/en/marine-traffic/).
