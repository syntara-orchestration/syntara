import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    globals: true,
    environment: 'happy-dom',
    mockReset: true,
    setupFiles: ['./packages/syntara-ui/src/test/setup.ts'],
    include: ['packages/*/src/**/*.{test,spec}.{js,jsx,ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: ['node_modules/', '**/dist/', '**/*.config.*', '**/mockData', '**/*.d.ts'],
      cleanOnRerun: true, // Clean coverage before each run
      all: false, // Don't collect coverage from all files, only tested ones
    },
  },
  resolve: {
    alias: {
      '~': new URL('./packages', import.meta.url).pathname,
    },
  },
})
