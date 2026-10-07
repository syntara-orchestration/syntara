import babel from '@rolldown/plugin-babel'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import { playwright as playwrightUntyped } from '@vitest/browser-playwright'
import { defineConfig } from 'vitest/config'
import type { BrowserProviderOption } from 'vitest/node'

type PlaywrightFactory = (options?: { launchOptions?: { headless?: boolean } }) => BrowserProviderOption
const playwright = playwrightUntyped as unknown as PlaywrightFactory

// Browser mode configuration for component tests
// Use this for tests that require real browser APIs (e.g., IntersectionObserver, ResizeObserver)
// Run with: npm run test:browser
export default defineConfig({
  plugins: [react(), babel({ presets: [reactCompilerPreset()] })],
  test: {
    globals: true,
    // Browser mode with Playwright (Vitest 4.x factory pattern)
    browser: {
      enabled: true,
      provider: playwright({
        launchOptions: {
          headless: true,
        },
      }),
      instances: [{ browser: 'chromium' }],
      // Enable screenshots on failure
      screenshotFailures: true,
    },
    setupFiles: './src/test/setup.ts',
    css: true,
    // Only run tests marked for browser mode
    include: ['**/*.browser.test.{ts,tsx}'],
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      exclude: [
        'node_modules/',
        'src/test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/mockData',
        'dist/',
        'e2e/',
        '**/*.test.{ts,tsx}',
        '**/*.spec.{ts,tsx}',
      ],
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
    },
  },
})
