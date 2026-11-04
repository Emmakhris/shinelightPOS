import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: { environment: 'node', include: ['src/**/*.test.{ts,tsx}'] }, // e2e/ is run by Playwright
})
