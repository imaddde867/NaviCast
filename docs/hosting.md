# Hosted live map

NaviCast uses one Cloudflare Worker with static assets at `navicast.imadlab.com`. The Worker adapts the public Digitraffic AIS REST snapshot to the same response fields used by the Python API. It computes constant-course projections from each original observation timestamp and exposes the existing map, filters and JSON/CSV downloads.

A canonical snapshot is cached for 30 seconds per Cloudflare location. The hosted REST feed treats observations older than five minutes as stale; the local MQTT/demo view retains its one-minute threshold. This allows for upstream snapshot latency without replacing source timestamps. Upstream requests use gzip compression and an identifying `Digitraffic-User` header. Invalid or old observations are excluded. An upstream failure returns a visible service error; it never substitutes synthetic data.

GitHub Pages could host the HTML but cannot run the dynamic API or persistent MQTT collector. Supabase could retain history, but would add storage, migrations and access policies that the current public map does not need. The existing imadlab Supabase project is unchanged.

The optional Python/PostgreSQL/MQTT stack is the legacy local collection path, superseded by the Worker cron archive. The collector on this branch writes to Cloudflare D1 (binding `AIS_ARCHIVE_DB`, free tier only) and is undeployed: no database exists, `wrangler.jsonc` holds a placeholder `database_id`, and the owner has not yet confirmed the Workers Free plan. R2 is not used because activating it requires a payment method. Retention is a weekly download, local verification and owner-approved deletion; a storage guard pauses collection at 350 MB. No archive history is served by the public Worker. See [evaluation and deployment gates](evaluation.md).

## Release

1. Run Python tests and `npm test`.
2. Run `npm run check:deploy` to validate the Worker bundle and configuration.
3. Review and merge the release PR after CI passes.
4. Authenticate with Wrangler and run `npm run deploy`.
5. Verify HTTPS `/health` (archive freshness: 503 until the first archived minute exists and again if collection stops for five minutes), `/meta`, `/vessels`, vessel detail and both export formats. Inspect desktop/mobile map rendering and browser console.

Cloudflare provisions DNS and TLS for the Worker custom domain. The configuration names only the NaviCast subdomain. Do not replace the portfolio apex records.

Runtime limits and quotas depend on the Cloudflare account plan. This deployment does not change the plan or introduce paid storage. The 4.5 ms collector figure in the evaluation notes is a local Node probe, not Workers CPU time, so Workers Free CPU compliance is unverified. At high traffic, review request quotas and feed load before increasing refresh frequency.

Sources: [Workers static assets](https://developers.cloudflare.com/workers/static-assets/), [custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/), [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [Digitraffic marine API](https://www.digitraffic.fi/en/marine-traffic/).
