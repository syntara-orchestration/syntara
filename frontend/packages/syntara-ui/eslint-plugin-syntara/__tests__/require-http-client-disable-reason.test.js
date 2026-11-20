import { readdir, readFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import ansiblePlugin from '@ansible/eslint-plugin'
import { RuleTester } from 'eslint'
import tseslint from 'typescript-eslint'
import { describe, expect, it } from 'vitest'
import rule from '../rules/require-http-client-disable-reason.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
  },
  plugins: { '@ansible': ansiblePlugin },
})

const SUPPRESSION_RULE_ID = 'syntara/require-http-client-disable-reason'
const IGNORED_DIRECTORIES = new Set([
  '.git',
  'coverage',
  'dist',
  'node_modules',
  'playwright-report',
  'storybook-static',
  'test-results',
])

function parseDisableComment(commentValue) {
  const normalized = commentValue
    .split(/\r?\n/u)
    .map((line) =>
      line
        .trim()
        .replace(/^\*\s?/u, '')
        .trim()
    )
    .filter(Boolean)
    .join(' ')
  const match = normalized.match(/^eslint-disable(?:-(?:next-)?line)?(?:\s+|$)([\s\S]*)$/u)
  if (!match) return null

  const [ruleList] = match[1].split('--')
  return {
    ruleIds: ruleList
      .split(',')
      .map((ruleId) => ruleId.trim())
      .filter(Boolean),
  }
}

function isForbiddenDisable(commentValue) {
  const directive = parseDisableComment(commentValue)
  return directive && (directive.ruleIds.length === 0 || directive.ruleIds.includes(SUPPRESSION_RULE_ID))
}

async function getSourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []

  for (const entry of entries) {
    const path = join(directory, entry.name)
    if (entry.isDirectory() && !IGNORED_DIRECTORIES.has(entry.name)) {
      files.push(...(await getSourceFiles(path)))
    } else if (/\.(?:js|jsx|ts|tsx)$/u.test(entry.name)) {
      files.push(path)
    }
  }

  return files
}

ruleTester.run('require-http-client-disable-reason', rule, {
  valid: [
    { code: 'const request = () => undefined' },
    { code: '// eslint-disable-next-line no-console\nconsole.log("auth flow")' },
    { code: '// eslint-enable @ansible/no-unapproved-http-client\nconst request = () => undefined' },
    {
      code: '// eslint-disable-next-line @ansible/no-unapproved-http-client -- auth exchange before client initialization\nfetch("/api/v1/auth/token")',
    },
    {
      code: 'fetch("/api/v1/auth/token") // eslint-disable-line @ansible/no-unapproved-http-client -- auth exchange before client initialization',
    },
    {
      code: '/* eslint-disable no-console, @ansible/no-unapproved-http-client -- auth exchange before client initialization */\nconst request = () => undefined',
    },
    {
      code: '/* eslint-disable\n@ansible/no-unapproved-http-client -- auth exchange before client initialization\n*/\nconst request = () => undefined',
    },
    {
      code: '/* eslint-disable -- temporary all-rule exception with a reason */\nconst request = () => undefined',
    },
  ],
  invalid: [
    {
      code: '// eslint-disable-next-line @ansible/no-unapproved-http-client\nfetch("/api/v1/auth/token")',
      errors: [{ messageId: 'missingReason' }],
    },
    {
      code: 'fetch("/api/v1/auth/token") // eslint-disable-line @ansible/no-unapproved-http-client',
      errors: [{ messageId: 'missingReason' }],
    },
    {
      code: '/* eslint-disable no-console, @ansible/no-unapproved-http-client */\nconst request = () => undefined',
      errors: [{ messageId: 'missingReason' }],
    },
    {
      code: '/* eslint-disable\n@ansible/no-unapproved-http-client\n*/\nconst request = () => undefined',
      errors: [{ messageId: 'missingReason' }],
    },
    {
      code: '// eslint-disable-next-line @ansible/no-unapproved-http-client --   \nfetch("/api/v1/auth/token")',
      errors: [{ messageId: 'missingReason' }],
    },
  ],
})

describe('HTTP-client suppression directive policy', () => {
  it('identifies blanket disables and disables of the suppression checker', () => {
    expect(isForbiddenDisable(' eslint-disable ')).toBe(true)
    expect(isForbiddenDisable(' eslint-disable syntara/require-http-client-disable-reason -- temporary')).toBe(true)
    expect(isForbiddenDisable(' eslint-disable @ansible/no-unapproved-http-client -- auth flow')).toBe(false)
  })

  it('rejects blanket disables and disables of the suppression checker in source', async () => {
    const sourceFiles = await getSourceFiles(resolve('.'))
    const findings = []

    for (const path of sourceFiles) {
      const code = await readFile(path, 'utf8')
      const { ast } = tseslint.parser.parseForESLint(code, {
        ecmaVersion: 'latest',
        filePath: path,
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      })

      for (const comment of ast.comments ?? []) {
        if (isForbiddenDisable(comment.value)) findings.push(`${path}:${comment.loc.start.line}`)
      }
    }

    expect(findings).toEqual([])
  })
})
