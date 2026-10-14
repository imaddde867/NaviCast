import { cloudflareTest, readD1Migrations } from '@cloudflare/vitest-plugin';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [cloudflareTest(async () => ({
    wrangler: { configPath: './wrangler.jsonc' },
    miniflare: {
      d1Databases: { AIS_ARCHIVE_DB: 'navicast-test-only' },
      bindings: { TEST_MIGRATIONS: await readD1Migrations('./migrations') },
    },
  }))],
  test: {
    // workerd cannot read Vitest's host filesystem transform cache.
    fsModuleCache: false,
    include: ['tests/runtime/*.test.mjs'],
    reporters: ['default', 'junit'],
    outputFile: { junit: 'reports/runtime.xml' },
  },
});
