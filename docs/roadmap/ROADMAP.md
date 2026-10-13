# NaviCast roadmap

Status: plan of record. Issues #6 to #28 are open on GitHub; prototype PRs #29 (land mask) and #30 (collector) are drafts. Update this file as work lands.

## Goal

NaviCast should be three things at once, from one codebase:

1. **Portfolio showpiece.** A live, polished Baltic vessel map whose claims are all true and measured.
2. **Reliable tool.** A public API and map that run unattended, degrade honestly, and flag and measure wrong paths and reduce them over time.
3. **Rigorous research.** A reproducible 30-minute vessel-position forecasting benchmark with honest baselines, vessel-level splits and published negative results if the model does not help.

## Where we are (checked 2026-10-13; method in the evidence column)

| Fact | Evidence |
|---|---|
| Production predictor is constant-course dead reckoning. No model is served. | `cloudflare/worker.mjs` `normalize()`; `/meta` reports `dead_reckoning` |
| Historical "154 m mean / 11 m median, R2 1.0000" is invalid: scores used predictions snapped to held-out test targets, on a random row split. | notebook cell 18 at commit `9aa6362` |
| Straight-line projections cross land; the rate depends on coastline resolution (table below). | `scripts/baseline/` |
| Three projection implementations disagree (geometry, guards, speed ceiling, stale threshold). | `prediction_service.py`, `worker.mjs`, `static/index.html` |
| Browser silently renders at most 500 vessels; oldest fixes dropped. | `static/index.html:884` |
| Ship type is unknown for all vessels in the hosted feed. | live `/vessels` |
| No record of predictions vs reality exists. Digitraffic offers no archive. | checked on digitraffic.fi, 2026-10-13 |
| The map footer credits OSM tiles only; Digitraffic data is CC BY 4.0. | map footer; #7 |

Land conflicts on a live snapshot (2026-10-13 10:30 UTC, 171 projected vessels), two separate metrics per coastline resolution:

| Metric | Natural Earth 10m | OSM-derived 111 m mask |
|---|---|---|
| Projected endpoint on land | 10.5% | 11.7% |
| Path touches land | 18.1% | 24.6% |
| In-water starts whose path crosses land | 10.8% | 19.4% (31/160) |

## Target architecture (single implementation)

```text
Digitraffic REST (locations, vessels metadata)
        |
 Cloudflare Worker  --serve-->  Map + JSON/CSV API   (one projection code path, server side)
        |  cron (1 min)
        v
   R2: ais/YYYY/MM/DD/HH/mm.ndjson.gz   (raw, append-only, schema-versioned)
   R2: meta/YYYY/MM/DD.json.gz          (daily vessel metadata)
   R2: tracks/latest.json               (rolling recent per-vessel tracks; or Durable Object, #8 decides)
        |
 offline Python (research/, owner's machine)  -->  evaluation, training, reports
        -->  model artifact (JSON tree ensemble, model_version)  -->  Worker
```

Constraint: the Worker is stateless. Smoothed dead reckoning, track-statistic features and track matching need the last roughly 30 minutes of observations per vessel, so recent tracks must live in a store the Worker can read (a rolling R2 object written by the cron run, or a Durable Object). #8 picks one and states its read cost.

Rules: one projection implementation (in the Worker); the browser only draws what the API returns; Python exists only for offline research; the FastAPI/MQTT/PostgreSQL stack is superseded, then removed (#26). Raw archive objects are not deleted by rule; compaction is offline and a local backup is kept (#8, #13). CI holds no secrets, so jobs that need R2 credentials run on the owner's machine or in Cloudflare (#12, #13).

## Tracks and milestones

| Milestone | Outcome | Issues |
|---|---|---|
| M0 Honest baseline | No false claims; data licensing and attribution; decision recorded; golden projection fixture; land conflicts flagged; no silent cap in the UI | #8 #6 #10 #11 #12 #7 |
| M1 Data | Own AIS archive and daily metadata accumulating; archive readable offline; historical sets profiled | #9 #14 #15 #13 |
| M2 Evaluation | Protocol and pre-registration, splitters and leakage guard, streaming evaluator, post-mortem, pilot baseline benchmark | #16 #17 #18 #20 #19 |
| M3 Model | Learned residual model, water-aware prediction spike, uncertainty | #21 #22 #23 |
| M4 Product | Full-fleet rendering, API contract, stack retired, public scoreboard | #25 #24 #26 #27 |
| M5 Portfolio | Case study and write-up | #28 |

Dependency sketch (`depends_on` in each issue is authoritative):

```text
#8 -> #9 -> #14 -> #21
#9 -> #13 -> #27
#16 -> #17 -> #18
#9 + #16 + #18 -> #19 -> #21 -> #23
#12 + #7 -> #10 -> #22 <- #19;  #10 -> #11 -> #25
#16 + #17 + (#15 or #9) -> #20 -> #28 <- #19
#8 + #9 -> #26;  #19 + #13 -> #27
#22 (spike) -> #21 v2 lane features (follow-up)
```

## Order of work

1. **#6 + #7.** Remove false claims; add Digitraffic attribution and the data and retention policy. Cheap and public-facing.
2. **#8 (one page) + #9.** The data clock is the long pole: nothing in M2 can be run on real data until weeks of archive exist. #13 follows as soon as #9 has written its first objects, so the archive can be fetched and backed up.
3. **#10 + #11 + #12 golden fixture.** The golden fixture lands first, because #10 and #11 change projection behaviour.
4. **#16, #17 and #18 while data accumulates.** #14 and #15 fit alongside.
5. **#19 after 3-4 weeks of data**, then #20 and #28.

Deferred: #21, the #22 spike, #23, #24, #27, #25. #26 whenever convenient (the notebook archive step is a cheap deletion once #9 is verified).

## Principles for claims

A result is a pilot unless it spans seasons; every reported number carries its date and data window. Abstention is scored: a predictor that withholds or clips projections is reported with its coverage on identical rows. A locked final test period stays untouched until the end, and one pre-registered endpoint (#16) decides whether a model counts as an improvement.

## Working agreements (instructions for contributors)

1. **Measure first.** Every change that affects projections must report before/after numbers from `research/evaluate.py` or `scripts/baseline/`. No number enters README, docs, the imadlab page or a post unless a script in the repo reproduces it.
2. **Never split rows randomly.** Splits are by vessel (generalisation) and by time (forecasting), with purge gaps. A test that fails on row-level leakage is mandatory (#17).
3. **Test labels never touch predictions.** No snapping, clipping or tuning with held-out targets. Post-processing may use only information available at prediction time (coastline, fairway data, past observations). Assets are built from training data only.
4. **Pre-register thresholds.** Success criteria for models are written in #16 before any model result is seen. Negative results are published.
5. **Baselines are first-class.** Always report persistence and dead reckoning beside any model, same rows, same metric.
6. **One implementation.** Do not add a second serving path. Research code may live in `research/`; it must not be required at runtime.
7. **Licences and data.** Third-party data (Digitraffic: CC BY 4.0; OSM land mask: ODbL; IEEE DataPort and DMA sets: check terms) is never committed without a recorded licence note (#7). Raw research data stays out of git.
8. **No deploy, bucket creation or push to `main` without the owner.** Work on branches; open PRs.
9. **Claims in UI are conservative.** "Straight-line estimate" is not "forecast"; coast conflicts are flagged, not hidden; the UI states "not for navigation" (#11).
10. **Reproduce the baseline** with `scripts/baseline/README.md` before and after touching projection code.

## Out of scope (for now)

Weather and current modelling, routing to destinations, collision avoidance, authentication, mobile app, paid data sources.

## Open questions

- Workers Free vs Paid plan: is 10 ms CPU enough for the per-minute collector and for reading recent tracks? (#8, #9)
- Where do recent tracks live for the Worker, and what does reading them cost per request? (#8)
- Do leisure craft appear in the Digitraffic feed, and how are removal requests handled against an append-only archive? (#7, #8)
- Can quota exhaustion from API abuse stop the cron collector? Unverified. (#24)
- Licence of the IEEE DataPort Baltic set; DMA download availability. (#15)
- Is Finnish inland water (lakes, canals) worth modelling, or do we declare it unresolved? (#10, #22)


## Draft ID to issue number

Issue titles and some documents use the roadmap IDs below.

| Draft ID | Issue |
|---|---|
| D01 | #8 |
| D02 | #6 |
| D03 | #10 |
| D04 | #9 |
| D05 | #14 |
| D06 | #15 |
| D07a | #16 |
| D07b | #17 |
| D07c | #18 |
| D08 | #20 |
| D09 | #19 |
| D10 | #21 |
| D11 | #22 |
| D12 | #23 |
| D13a | #11 |
| D13b | #25 |
| D14 | #24 |
| D15 | #26 |
| D16 | #12 |
| D17 | #27 |
| D18 | #28 |
| D20 | #7 |
| D21 | #13 |
