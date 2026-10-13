# Prediction evaluation data

The hosted Worker is stateless and does not retain vessel history. This branch contains an undeployed archive collector and an experimental offline evaluator. No archive continuity or forecasting accuracy has been established.

## Archive prototype

The current prototype writes one gzipped NDJSON object per scheduled UTC minute to R2, keyed as `ais/YYYY/MM/DD/HH/mm.ndjson.gz` in `navicast-ais-archive` (binding `AIS_ARCHIVE`). The key comes from `event.scheduledTime`, so a delayed invocation does not move its data into the following minute. A retry of the same scheduled minute uses the same key. The gzip body has content type `application/gzip`.

The collector reuses the Worker's validated raw snapshot loader. Its schema header contains `schema`, `fetched_at`, `source`, `count` and `data_updated_at`. Vessel rows contain `mmsi`, `lat`, `lon`, `timestampExternal`, `age_s`, `sog`, `cog`, `heading`, `rot`, `navStat`, `posAcc` and `raim`. Raw motion sentinels and stale observations are retained for offline filtering. Invalid vessel identifiers and positions are excluded; empty or malformed snapshots fail without writing an archive object. Scheduled failures are logged and propagated to Cloudflare.

Source: [Fintraffic / digitraffic.fi](https://www.digitraffic.fi/en/marine-traffic/), license [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Archive rows select upstream fields and add observation age; evaluation outputs also carry attribution. Raw archive files and metadata must remain private and uncommitted. The proposed removal process in issue #7 remains an owner decision; publication of a contact address does not implement exclusion or deletion.

## Storage and deployment gate

The prototype R2 binding is not an approved storage decision. On 2026-10-13 the owner inspected R2 activation: the checkout explicitly uses the card on file, creates a renewable usage-billed subscription and permits payment-method preauthorization. Activation is therefore excluded under the no-card constraint. Prepare the D1 compressed-blob-per-minute fallback in [#8](https://github.com/imaddde867/NaviCast/issues/8), subject to confirming Workers Free before provisioning or deployment. No cloud resource has been created by this work.

Free tiers only. Do not deploy until storage is chosen and provisioned by the owner. Do not add a lifecycle expiry rule: the proposed retention policy has no automatic age-based deletion. Offload, local backup, capacity limits and accepted removal requests require an approved operating procedure.

For an owner-approved R2 deployment, the remaining steps are:

- Owner creates the private archive bucket and verifies the account's plan and storage eligibility.
- Run `npm ci`, `npm test` and `npm run check:deploy`; a dry-run validates the bundle, not bucket existence or free-tier CPU compliance.
- Owner deploys and confirms minute objects decompress correctly and use scheduled-time keys.
- Measure deployed CPU, including the daily metadata invocation once implemented. The local `scripts/baseline/collector_cpu.mjs` probe on main is a preliminary Node measurement only; it cannot establish Workers CPU compliance.
- Verify daily metadata collection, collector freshness/health reporting, deliberate failure alerts, and archive continuity before declaring #9 complete. These are not implemented or verified by the pre-merge fixes alone.

## Experimental evaluation

```bash
python -m pip install -r research/requirements.txt
python research/make_synthetic.py /tmp/ais-demo
python research/evaluate.py /tmp/ais-demo --json /tmp/navicast-evaluation.json
python -m pytest research -q
```

Observations are deduplicated by vessel identifier and source timestamp. Only valid motion records are scored. Source observation time, not collection time, drives matching. Persistence and dead reckoning are evaluated on the same matched rows, overall and by speed bucket; errors are reported in metres. No training split is implemented.

The evaluator remains a prototype: the current fixed truth-matching tolerance, projection over matched elapsed time, whole-archive memory use and lack of vessel-level confidence intervals do not satisfy the protocol and streaming requirements in [#16](https://github.com/imaddde867/NaviCast/issues/16), [#17](https://github.com/imaddde867/NaviCast/issues/17) and [#18](https://github.com/imaddde867/NaviCast/issues/18). Do not publish its results as validated accuracy claims. Do not split AIS rows randomly or use held-out target positions in prediction code. Scientific-method changes require a reviewed protocol before implementation.

The feed's location endpoint does not contain ship type. Daily vessel metadata capture is still required from day one; joining that metadata into serving and evaluation is tracked separately in #14. Sparse tracks and repeated upstream snapshots reduce usable evaluation coverage. A continuity check must treat a missing object, an empty snapshot or repeated `data_updated_at` as a gap.
