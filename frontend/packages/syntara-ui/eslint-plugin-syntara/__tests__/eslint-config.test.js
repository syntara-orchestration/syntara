import { ESLint } from 'eslint'
import { resolve } from 'node:path'
import tseslint from 'typescript-eslint'
import { describe, expect, it } from 'vitest'

const packageDirectory = import.meta.dirname ? resolve(import.meta.dirname, '../..') : process.cwd()

// Load the package's real ESLint configuration. The test does not copy or recreate its rules.
const eslint = new ESLint({
  cwd: packageDirectory,
  overrideConfigFile: resolve(packageDirectory, 'eslint.config.js'),
  // Import restrictions only need syntax. Skip the real app's type-aware rules so
  // this focused config test does not build the whole TypeScript project.
  overrideConfig: {
    ...tseslint.configs.disableTypeChecked,
    rules: {
      ...tseslint.configs.disableTypeChecked.rules,
      'max-lines-per-function': 'off',
    },
  },
})

async function lintStory() {
  return eslint.lintText(
    "import type { Meta } from '@storybook/react-vite'\nimport { SearchIcon } from '@patternfly/react-icons'\n\nvoid SearchIcon\ntype StoryMeta = Meta\nvoid ({} as StoryMeta)\n",
    { filePath: 'src/test/restricted-story-imports.stories.tsx' }
  )
}

describe('ESLint Storybook import restrictions', () => {
  it('rejects the Vite Storybook framework import', async () => {
    const [result] = await lintStory()

    const violation = result.messages.find(({ ruleId }) => ruleId === '@typescript-eslint/no-restricted-imports')

    expect(violation).toEqual(
      expect.objectContaining({
        severity: 2,
        message: expect.stringContaining('Use @storybook/tanstack-react'),
      })
    )
  })

  it('retains the existing icon restriction in stories', async () => {
    const [result] = await lintStory()

    expect(result.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          ruleId: 'no-restricted-imports',
          severity: 1,
          message: expect.stringContaining('Use RhUi* icons'),
        }),
      ])
    )
  })
})
