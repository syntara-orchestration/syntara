import { ESLint } from 'eslint'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const packageDirectory = process.cwd()
// Load the package's real ESLint configuration. The test does not copy or recreate its rules.
const eslint = new ESLint({
  cwd: packageDirectory,
  overrideConfigFile: resolve(packageDirectory, 'eslint.config.js'),
  // The synthetic source has no meaningful function length; keep this unrelated rule out of the test.
  overrideConfig: { rules: { 'max-lines-per-function': 'off' } },
})

async function lintStory(code) {
  // lintText uses in-memory source, while filePath applies the real Storybook file-glob config.
  return eslint.lintText(code, {
    filePath: 'src/components/layout/SynPanelStack.stories.tsx',
  })
}

describe('ESLint Storybook import restrictions', () => {
  it('rejects the Vite Storybook framework import', async () => {
    const [result] = await lintStory("import type { Meta } from '@storybook/react-vite'")

    expect(result.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          ruleId: '@typescript-eslint/no-restricted-imports',
          severity: 2,
          message: expect.stringContaining('Use @storybook/tanstack-react'),
        }),
      ])
    )
  })

  it('retains the existing icon restriction in stories', async () => {
    const [result] = await lintStory("import { SearchIcon } from '@patternfly/react-icons'")

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
