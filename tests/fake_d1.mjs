// Minimal in-memory stand-in for the D1 binding, covering only the statements the Worker issues.
// Mirrors SQLite semantics that matter here: a duplicate key errors unless ON CONFLICT DO NOTHING is used.
export function fakeD1({ size = 1000, fail } = {}) {
  const db = { rows: new Map(), queries: [], size };
  const execute = async (sql, args) => {
    db.queries.push({ sql, args });
    if (fail) throw fail;
    const meta = { size_after: db.size };
    if (/^SELECT 1$/.test(sql)) return { results: [{ 1: 1 }], meta };
    if (/^INSERT INTO archive_objects/.test(sql)) {
      const [key, kind, scheduled_at, fetched_at, data_updated_at, count, body] = args;
      if (db.rows.has(key)) {
        if (!/ON CONFLICT\(key\) DO NOTHING$/.test(sql)) throw new Error('UNIQUE constraint failed: archive_objects.key');
        return { results: [], meta: { ...meta, changes: 0 } };
      }
      db.rows.set(key, { key, kind, scheduled_at, fetched_at, data_updated_at, count, body });
      return { results: [], meta: { ...meta, changes: 1 } };
    }
    if (/^SELECT fetched_at FROM archive_objects WHERE key >= 'ais\/' AND key < 'ais0' ORDER BY key DESC LIMIT 1$/.test(sql)) {
      const newest = [...db.rows.values()].filter(r => r.key >= 'ais/' && r.key < 'ais0')
        .sort((a, b) => (a.key < b.key ? 1 : -1))[0];
      return { results: newest ? [{ fetched_at: newest.fetched_at }] : [], meta };
    }
    throw new Error(`fake D1: unexpected SQL ${sql}`);
  };
  db.prepare = sql => ({
    bind: (...args) => ({ run: () => execute(sql, args) }),
    run: () => execute(sql, []),
    first: async () => (await execute(sql, [])).results[0] ?? null,
  });
  return db;
}
