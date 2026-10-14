# Final CI and main protection rollout

The five jobs in `.github/workflows/ci.yml` cover Python/PostgreSQL/research,
Node unit/golden contracts, actual workerd/D1, actual Chromium/Leaflet, and
Wrangler/Docker/configuration. Separate duplicate workflows are removed.
Testcase inventories reject passing subsets and unexpected skips; coverage
tracks uncovered counts. Projection, browser and scientific mutations run in
isolated temporary copies. Reports and browser failure traces/screenshots are
uploaded even on failure. Explicit Bash uses `-eo pipefail`, so piping build
or Docker logs through `tee` cannot hide a failed check. CI uses Python 3.11, Node 22, pinned dependencies,
read-only repository permissions, local services and no production secrets.
`check:deploy` is Wrangler **dry-run only**. No deployment job is added.

## Dependency and review order

The integration branch combined #39, #40, #41, #42, #44, #45 and #46 for
verification. On 2026-10-14, the reviewed focused PRs were merged individually
with successful current-head CI; #45 was retargeted after #42, and final #47
was reconciled/retargeted to main before its own green merge. The aggregate
branch remained a verification aid, not an enormous replacement PR.

## Protection activation

`.github/main-protection.json` is a concrete GitHub REST protection payload:
up-to-date branches, all five checks, required pull requests, resolved
conversations, administrator enforcement, no force pushes and no deletions.
No bypass identities are added. Imad explicitly approved zero mandatory
review approvals and no last-push-review gate on 2026-10-14: GitHub lists only
the PR-author/owner as a collaborator, so an independent write-access reviewer
requirement would make their own PRs unmergeable. The implementation PRs remain
open for owner review; production deployment approval stays manual.
Check providers are inferred from the established GitHub Actions checks.
The verified live response binds all five to GitHub Actions app 15368. Send
`checks` without legacy `contexts`: GitHub rejects the ambiguous combined
request with 422. The committed checks-only payload was accepted and verified.

Protection was activated only after the final workflow was merged and green
on **main**. To reproduce the reviewed owner-only application:

```bash
gh run list --branch main --workflow ci.yml --limit 5
gh api --method PUT repos/imaddde867/NaviCast/branches/main/protection \
  --input .github/main-protection.json
gh api repos/imaddde867/NaviCast/branches/main/protection
```

Confirm exactly the five contexts and `enforce_admins.enabled=true` in the
response. Do not apply missing checks prematurely and strand earlier PRs.
The source for this payload is [GitHub's branch protection REST API](https://docs.github.com/en/rest/branches/branch-protection#update-branch-protection).

For the acceptance probe, open a temporary PR with a deliberate critical
projection-test failure. Confirm the check fails and GitHub reports merge
blocked by the required check; close the probe and delete its own branch.
Do not attempt to merge the defect. The local mutation campaigns already prove
assertion sensitivity; this additional probe proves repository enforcement.

Protection and the merge-blocking probe are **verified complete**, as recorded
below. The source checks-only payload matches the applied policy.
No real-data forecasting quality evaluation has run; source-coastline
regeneration is pending the original ZIP. Production deployment still requires
manual owner approval through the existing deployment process.

## Verified GitHub execution

[Run 38603815976](https://github.com/imaddde867/NaviCast/actions/runs/38603815976)
passed all five jobs on the reviewed pipefail fix `82c483f` (2026-10-14).
Python **3.11.17** ran 142 tests in 2.96 s; Node ran 83 in 966.93 ms;
Chromium ran 12 in 14.6 s; workerd/D1 ran 12. All testcase inventories and
Python/Node/browser coverage gates passed, with no skips/deselections.
All four projection, three browser and three scientific mutations were detected.
Docker HTTP smoke and the 574,527-byte bundle passed inside CI.
Whole-job durations: Python 42 s, Node 15 s, runtime 14 s, browser 80 s,
build 30 s. These first measurements include setup/uploads and are not an
established performance budget; timeouts bound jobs to 10/15 minutes.

## Completed enforcement evidence (2026-10-14)

All eight hardening PRs are merged. Main `61c1825` passed all five jobs in
[run38617255513](https://github.com/imaddde867/NaviCast/actions/runs/38617255513):
142 Python cases / 2.49 s,83 Node / 786.71 ms,12 workerd / 2.01 s,12 Chromium / 11.1 s;
whole-job times35s/17s/16s/68s/45s respectively (including setup/uploads);
complete inventories and coverage gates, zero skips/deselections, all ten
software/scientific mutations detected, Docker HTTP smoke and bundle passed.
An independent review agent recommended the original and reconciled final
workflow before the authorized merges.

Live REST verification confirmed strict/up-to-date branches, mandatory PRs,
all five Actions-bound checks, administrator enforcement, resolved conversations,
zero required review count as explicitly approved, and no bypass/force pushes/
deletions. Main itself remained green.

[Probe #48](https://github.com/imaddde867/NaviCast/pull/48) suppressed only the
land-conflict flag. All83 Node cases executed; five actual golden/land-null
assertions failed. The four other required jobs passed. GitHub reported
`mergeStateStatus=BLOCKED` for a non-draft, conflict-free PR based on current main,
without a missing-review gate. See [the failing run](https://github.com/imaddde867/NaviCast/actions/runs/38617982063)
and [recorded result](https://github.com/imaddde867/NaviCast/pull/48#issuecomment-6175821684).
The probe was closed without merging and its temporary remote branch deleted.
No deliberate defect reached main, no production deployment occurred, and
source-ZIP regeneration/locked real-data quality evaluation remain unverified.
