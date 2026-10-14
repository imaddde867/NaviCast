# Synthetic scientific validation, separate from forecasting claims

This PR extends #16–#18 without completing the locked real-data protocol or
running a forecasting benchmark. The prototype's ±60-second matching rule,
earlier-target tie, matched elapsed time and percentile rule are preserved.
JSON now labels those rules `prototype-1`, explicitly **unvalidated**, including
units/scales and the fact that production caps are not applied. A fixed expected
rule descriptor and tolerance-edge tests prevent silent scoring changes.

Independent equatorial great-circle references verify 111195.0802335329 metres
for one degree, the same distance across the date line, and pi times the mean
Earth radius for antipodes. Perturbing future target coordinates does not change
any forecast input; it does change scored truth as it should.

Every horizon counts all source origins, invalid motion, unmatched eligible
targets and matched rows. Predictors remain on the identical matched population;
nonfinite predictions are counted as missing, coverage is explicit, and their
error percentile uses only finite predictions. A toy abstaining predictor
retains its matched row with zero coverage instead of disappearing. Existing
finite-result medians and matching behavior are unchanged.

`research/splits.py` operates on `(MMSI, origin_ms, target_ms)` windows and
requires a caller-supplied locked half-open period. Any window overlapping it
is excluded, including a training label that crosses into it. Vessel partitions
take explicit disjoint IDs; adjacent/duplicate rows stay together. Time splits
require explicit validation/test boundaries and purge gap. The verifier rejects
overlapping indices, vessel leakage, target-time leakage and malformed policy
inputs. `training_rows` accepts a validated partition and returns only its
training windows; a full-archive or random-row partition is rejected. No training
pipeline exists yet; these utilities must be adopted by future training/asset
builders, not treated as a retroactive validation of historical models.

`research/uncertainty.py` resamples complete vessels for paired median-error
improvements, with per-observation weighting explicitly reported. Seed and draw
count are mandatory. One-vessel intervals and nonfinite/unpaired errors reject.
The independent five-vessel example yields a 10-metre point improvement and
[0,20] metre interval. Replicating each vessel's dependent rows 100 times leaves that
interval unchanged, demonstrating that rows are not treated as independent.
This helper is not wired into the prototype CLI as a validated accuracy report.

Run `python -m pytest research -q -ra` after installing pinned research
requirements. Fifteen new synthetic cases cover the above. Initially 5 of 11
cases failed due to absent accounting/splits/bootstrap; after implementation
and explicit rule/input checks, **131 total Python cases pass** (including the
existing PostgreSQL suite), no skips, 0.71 seconds locally.

`python scripts/check_research_mutations.py` requires a passing temporary-copy
baseline, then demonstrates failures for row bootstrap, omitted purge and a
one-millisecond matching-tolerance drift. It disables bytecode writes because
same-size/same-second source mutations can otherwise reuse stale Python cache
files and falsely appear to survive. The first symmetric two-vessel example
did not detect row bootstrap, so it was replaced with the five-vessel reference
above. All three representative scientific defects are now detected in CI.

Remaining #16–#18 decisions: reviewed horizon-proportional tolerance, origin
subsampling, minimum-vessel threshold, locked archive dates and improvement
margin; day-sharded evaluation/peak-memory measurements; actual training asset
integration and registered split use. The current matching tolerance is a
protected prototype behavior, not the registered final protocol. Independent
archived AIS evaluation stays outside PR CI, and accuracy claims remain barred.
