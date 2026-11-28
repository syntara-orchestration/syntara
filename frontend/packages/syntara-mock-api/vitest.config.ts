import { defineConfig } from 'vitest/config'

const mutationTimeoutValue = process.env.SYNTARA_MUTATION_VITEST_TIMEOUT_MS
const mutationTimeoutMs = mutationTimeoutValue === undefined ? undefined : Number(mutationTimeoutValue)

if (mutationTimeoutMs !== undefined && (!Number.isSafeInteger(mutationTimeoutMs) || mutationTimeoutMs < 1)) {
  throw new Error('SYNTARA_MUTATION_VITEST_TIMEOUT_MS must be a positive integer when set')
}

const mutationTimeoutOverrides =
  mutationTimeoutMs === undefined ? {} : { testTimeout: mutationTimeoutMs, hookTimeout: mutationTimeoutMs }

// https://vitest.dev/config/
export default defineConfig({
  test: {
    ...mutationTimeoutOverrides,
    globals: true,
    environment: 'node',
    include: ['src/**/*.test.ts'],
    exclude: ['**/node_modules/**', '**/dist/**'],
  },
})
