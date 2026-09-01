import { ESLint } from 'eslint'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const packageDirectory = process.cwd()
const eslint = new ESLint({
  cwd: packageDirectory,
  overrideConfigFile: resolve(packageDirectory, 'eslint.config.js'),
})

async function lintStory(code) {
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
          message: expect.stringContaining('Use RhUi* icons'),
        }),
      ])
    )
  })
})
