import { defineConfig, devices } from '@playwright/test'

const port = 8001

export default defineConfig({
  testDir: './e2e',
  // The tests share one database and build on each other (setup → sell → refund → close shift).
  workers: 1,
  fullyParallel: false,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    viewport: { width: 1366, height: 800 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'edge',
      // Use the installed Microsoft Edge: Windows (Smart App Control) can refuse to run
      // Playwright's own unsigned Chromium build. Set E2E_BROWSER=chromium to use that instead.
      use: {
        ...devices['Desktop Edge'],
        channel: process.env.E2E_BROWSER === 'chromium' ? undefined : 'msedge',
        viewport: { width: 1366, height: 800 },
      },
    },
  ],
  webServer: {
    command: 'npm run build && node e2e/server.mjs',
    url: `http://127.0.0.1:${port}/api/setup/status/`,
    reuseExistingServer: false,
    timeout: 180_000,
    env: { E2E_PORT: String(port) },
  },
})
