# Final CI and main protection rollout

The five jobs in `.github/workflows/ci.yml` cover Python/PostgreSQL/research,
Node unit/golden contracts, actual workerd/D1, actual Chromium/Leaflet, and
Wrangler/Docker/configuration. Separate duplicate workflows are removed.
Testcase inventories reject passing subsets and unexpected skips; coverage
tracks uncovered counts. Projection, browser and scientific mutations run in
isolated temporary copies. Reports and browser failure traces/screenshots are
uploaded even on failure. CI uses Python 3.11, Node 22, pinned dependencies,
read-only repository permissions, local services and no production secrets.
`check:deploy` is Wrangler **dry-run only**. No deployment job is added.

## Dependency and review order

The integration branch combines #39, #40, #41, #42, #44, #45 and #46 without
merging them to main. This final PR targets that branch so its diff contains
only consolidation and enforcement documentation/configuration. Review and
merge the focused PRs, reconciling coverage after #42; then retarget this final
PR to main and reconcile inventories/lockfile. The aggregate dependency branch
is a verification aid, not an enormous replacement implementation PR.

## Protection activation

`.github/main-protection.json` is a concrete GitHub REST protection payload:
up-to-date branches, all five checks, one approving review, stale reviews
dismissed, last-push approval, resolved conversations, administrator
enforcement, no force pushes and no deletions. No bypass identities are added.
Check providers are inferred from the established GitHub Actions checks.

After the final workflow is reviewed, merged and green on **main**, apply it:

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

Protection and the merge-blocking probe are **pending**, not claimed complete.
No real-data forecasting quality evaluation has run; source-coastline
regeneration is pending the original ZIP. Production deployment still requires
manual owner approval through the existing deployment process.
