import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const isShardedCoverage = process.env.CI === 'true' && Boolean(process.env.VITEST_COVERAGE_DIR)
const isCoverageRun = process.argv.includes('--coverage') || isShardedCoverage

// https://vitest.dev/config/
export default defineConfig({
  plugins: [
    react({
      babel: {
        // Disable the React Compiler during coverage runs. The compiler transforms
        // JSX into optimized code with internal branches that V8 tracks as real
        // conditions, producing phantom uncovered branches in lcov reports.
        // Upstream bug: https://github.com/facebook/react/issues/32950
        plugins: isCoverageRun ? [] : [['babel-plugin-react-compiler']],
      },
    }),
  ],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    mockReset: true,
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**', '**/playwright.config.ts', '**/*.browser.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reportsDirectory: process.env.VITEST_COVERAGE_DIR ?? 'coverage',
      reporter: isShardedCoverage ? ['json'] : ['text', 'json', 'json-summary', 'html', 'lcov'],
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
        '**/*.stories.*',
        '**/tanstackRouteTree.tsx',
      ],
    },
  },
})
