-- D1 archive of raw Digitraffic objects. Contract shared with cloudflare/collector.mjs
-- (writer) and scripts/archive/download_d1.py (reader). Keys: ais/YYYY/MM/DD/HH/mm.ndjson.gz
-- and meta/YYYY/MM/DD.json.gz, UTC. Timestamps are epoch milliseconds.
CREATE TABLE archive_objects (
  key TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('ais', 'meta')),
  scheduled_at INTEGER NOT NULL,
  fetched_at INTEGER NOT NULL,
  data_updated_at TEXT,
  count INTEGER NOT NULL,
  body BLOB NOT NULL
);
