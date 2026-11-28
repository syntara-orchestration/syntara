import path from 'node:path'

const reportDir = path.resolve(process.cwd(), process.env.SYNTARA_MUTATION_REPORT_DIR ?? 'reports/mutation')

export default {
  mutate: [
    'src/**/*.{js,jsx,ts,tsx}',
    'eslint-plugin-syntara/**/*.{js,jsx,ts,tsx}',
    '!**/*.test.{js,jsx,ts,tsx}',
    '!**/*.spec.{js,jsx,ts,tsx}',
    '!**/*.stories.{js,jsx,ts,tsx}',
    '!**/*.testFixtures.{js,jsx,ts,tsx}',
    '!**/*.d.ts',
    '!**/__tests__/**',
    '!**/test/**',
    '!**/tests/**',
    '!**/fixtures/**',
    '!**/__fixtures__/**',
    '!**/mockData/**',
    '!src/app/tanstackRouteTree.tsx',
  ],
  testRunner: 'vitest',
  vitest: {
    configFile: 'vitest.config.ts',
    related: true,
  },
  incremental: true,
  incrementalFile: path.join(reportDir, 'stryker-incremental.json'),
  reporters: ['progress', 'clear-text', 'html', 'json'],
  clearTextReporter: {
    reportMutants: false,
    reportTests: false,
    skipFull: true,
  },
  htmlReporter: {
    fileName: path.join(reportDir, 'ui.html'),
  },
  jsonReporter: {
    fileName: path.join(reportDir, 'ui.json'),
  },
  concurrency: 2,
  dryRunTimeoutMinutes: 15,
  timeoutMS: 15_000,
  cleanTempDir: 'always',
}
