import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  timeout: 30_000,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list'], ['junit', { outputFile: 'reports/browser.xml' }], ['html', { open: 'never', outputFolder: 'reports/browser-html' }]],
  use: {
    browserName: 'chromium',
    baseURL: 'http://127.0.0.1:18765',
    viewport: { width: 1280, height: 800 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  outputDir: 'reports/browser-artifacts',
  webServer: {
    command: 'python3 -m http.server 18765 --bind 127.0.0.1 --directory static',
    url: 'http://127.0.0.1:18765',
    reuseExistingServer: false,
  },
});
