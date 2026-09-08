import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { StorybookConfig } from '@storybook/tanstack-react'

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: [
    getAbsolutePath('@storybook/addon-docs'),
    getAbsolutePath('@storybook/addon-a11y'),
    getAbsolutePath('@storybook/addon-mcp'),
  ],
  framework: '@storybook/tanstack-react',
  core: {
    disableTelemetry: true,
  },
  features: {
    sidebarOnboardingChecklist: false,
  },
  // Storybook runs its own Vite instance and does not inherit server.watch from vite.config.ts,
  // so coverage report writes would trigger spurious page reloads without this.
  async viteFinal(config) {
    const { mergeConfig } = await import('vite')

    return mergeConfig(config, {
      server: {
        strictPort: true,
        watch: {
          ignored: ['**/coverage/**'],
        },
      },
    })
  },
}
export default config

function getAbsolutePath(value: string) {
  return dirname(fileURLToPath(import.meta.resolve(`${value}/package.json`)))
}
