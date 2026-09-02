import { ESLint } from 'eslint'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const packageDirectory = import.meta.dirname ? resolve(import.meta.dirname, '../..') : process.cwd()

// Load the package's real ESLint configuration. The test does not copy or recreate its rules.
const restrictedStoryFixture = 'eslint-plugin-syntara/__tests__/fixtures/restricted-story-imports.stories.tsx'
const eslint = new ESLint({
  cwd: packageDirectory,
  ignore: false,
  overrideConfigFile: resolve(packageDirectory, 'eslint.config.js'),
  // The fixture has no functions, so exclude this unrelated rule from the test.
  overrideConfig: { rules: { 'max-lines-per-function': 'off' } },
})

async function lintStory() {
  // This fixture is part of the TypeScript project, so type-aware rules use its real source.
  return eslint.lintFiles([restrictedStoryFixture])
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
  }, 30_000)

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
