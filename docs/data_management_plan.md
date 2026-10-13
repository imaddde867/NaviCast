# Data management

## Current sources and retention

The public Cloudflare Worker reads current Digitraffic Marine REST locations. It filters and normalizes observations, adds constant-course estimates and temporarily caches the snapshot. It does not retain vessel history or serve a trained model. The public API and downloads expose MMSI, positions, source timestamps and navigation fields, including speed, course, heading and navigation status.

The optional local MQTT/PostgreSQL pipeline stores those fields and the source message as JSONB. It deletes raw rows older than 24 hours and stored predictions older than one hour. These are code-defined retention periods. Its unauthenticated API and database must remain on a trusted network. Demo mode generates synthetic records without ingesting real AIS messages.

Source: [Fintraffic / digitraffic.fi](https://www.digitraffic.fi/en/marine-traffic/), license [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Data and estimates carry no guarantee of accuracy and must not be used for navigation. Vessel identifiers and movement patterns may identify people for some craft; whether leisure craft appear in this feed remains unverified.

## Proposed archive — not deployed

The draft collector will retain per-minute navigation observations and daily vessel metadata privately, without automatic age-based deletion. Compaction and backup will take place offline. Storage selection and the free-tier capacity/offload procedure remain decisions in [#8](https://github.com/imaddde867/NaviCast/issues/8) and [#13](https://github.com/imaddde867/NaviCast/issues/13). Capacity exhaustion must pause collection rather than introduce charges or silently discard data.

## Proposed removal process — owner approval and implementation pending

Use an existing private email address selected by Imad; the address has not been approved or published. Do not submit MMSI, vessel names, movement details or identity documents in public GitHub issues. Requests should identify the relevant vessel and explain the request privately; collect additional evidence only when needed.

Imad reviews each request and records its accepted scope: public display, future collection, existing research data, or all three. Approved removal is an explicit exception to retention without automatic expiry. NaviCast cannot remove observations from Digitraffic or copies controlled by other parties. Do not promise a response deadline before the owner selects one.

For an accepted request:

- Maintain a private exclusion register and apply it to the API, downloads, caches, collector and research loaders as appropriate to the accepted scope.
- Remove matching observations and metadata from controlled active archives, compacted datasets, recent tracks, fixtures and identifiable derived outputs. Rewrite mixed-vessel objects; hiding an API response alone is not archive deletion.
- Regenerate affected research outputs where necessary. Review any trained artifact that used the data rather than promising automatic model unlearning.
- Redact controlled backups as well. Quarantine a backup that cannot yet be rewritten and record deletion as incomplete. Reapply exclusions before any restored data is made available.
- Keep a minimal private record of scope, actions, verification and unresolved copies. Never commit the request correspondence or exclusion register.

This process is a recommendation, not an implemented service. Approval is still needed for the contact address, accepted-request scope, exceptional raw-data deletion, backup procedure and any response target.

## Publication review

Names, call signs and destinations are excluded from published screenshots and committed fixtures unless necessary and documented. The baseline fixture is minimized and uses stable pseudonyms; positions and timestamps can still make trajectories identifiable. Its earlier Git version retains original MMSIs. Replacing the current fixture does not erase Git history, clones or forks; history rewriting requires a separate owner decision.

`docs/dashboard.png` shows synthetic demo positions without vessel names or destinations. Historical model artifacts live under `archive/`; their evaluation is invalid and they are not used for serving.
