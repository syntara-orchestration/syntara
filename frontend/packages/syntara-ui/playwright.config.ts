import { defineConfig } from '@playwright/test'
import { currentsReporter } from '@currents/playwright'
import { config } from 'dotenv'
import path from 'path'
import { fileURLToPath } from 'url'

config({
  path: new URL('.env.local', import.meta.url).pathname,
  quiet: true,
})

import { isSkipWebServerForPlaywrightTests } from './e2e/playwrightWebServerEnv'

const uiPort = process.env.SYNTARA_E2E_PORT ?? '4173'
const apiPort = process.env.SYNTARA_E2E_API_PORT ?? '3300'
const baseURL = process.env.SYNTARA_E2E_BASE_URL ?? `http://localhost:${uiPort}`
const useWebServer = !isSkipWebServerForPlaywrightTests()

/**
 * Pinned clock for visual regression determinism.
 * Used by page-screenshots.spec.ts (page.clock.setFixedTime for the browser).
 * Mock API data uses hardcoded ISO strings relative to this date.
 */
export const VISUAL_REGRESSION_CLOCK = '2026-06-15T10:00:00Z'

export default defineConfig({
  globalSetup: './e2e/global-setup.ts',
  testDir: './e2e',
  testIgnore: [...(useWebServer ? [] : ['**/visual-regression/**']), '**/credential-types.spec.ts'],
  fullyParallel: true,
  workers: process.env.CI ? 3 : undefined,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [
    // 'line' prints errors inline as tests fail; 'list' buffers them to the end.
    // Use 'line' in CI so failures are visible in the live log without waiting
    // for the full suite to finish.
    [process.env.CI ? 'line' : 'list'],
    ['json', { outputFile: 'test-results/results.json' }],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ...(process.env.CURRENTS_PROJECT_ID && process.env.CURRENTS_RECORD_KEY ? [currentsReporter()] : []),
    // Last: prints listed playwright.md tests that passed so they can be removed.
    ['./e2e/xfailReporter.ts'],
  ],
  use: {
    baseURL,
    ignoreHTTPSErrors: !useWebServer,
    viewport: { width: 1280, height: 720 },
    // Limit artifacts to genuinely failing tests only — retries that eventually pass do
    // not produce uploads. Mirrors the ansible-ui Currents integration pattern.
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: useWebServer
    ? [
        {
          command: 'npm run start:mock-api',
          cwd: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..'),
          url: `http://localhost:${apiPort}/api/v1/workflows`,
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            PORT: apiPort,
          },
        },
        {
          command: process.env.CI
            ? `npm run build --prefix packages/syntara-ui && npm run preview --prefix packages/syntara-ui -- --port ${uiPort}`
            : `npm run start --prefix packages/syntara-ui -- --port ${uiPort}`,
          cwd: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..'),
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          // Build step in CI adds ~60s on top of the dev server startup
          timeout: 180_000,
          env: {
            VITE_API_URL: `http://localhost:${apiPort}`,
          },
        },
      ]
    : undefined,
})
