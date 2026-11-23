import { readdir, readFile } from 'node:fs/promises'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { findForbiddenDisableLines } from './sourcePolicy.js'

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const ignoredDirectories = new Set([
  '.git',
  '.stryker-tmp',
  'coverage',
  'dist',
  'node_modules',
  'playwright-report',
  'storybook-static',
  'test-results',
])

async function getSourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []

  for (const entry of entries) {
    const path = join(directory, entry.name)
    if (entry.isDirectory() && !ignoredDirectories.has(entry.name)) {
      files.push(...(await getSourceFiles(path)))
    } else if (/\.(?:js|jsx|ts|tsx)$/u.test(entry.name)) {
      files.push(path)
    }
  }

  return files
}

async function main() {
  const sourceFiles = await getSourceFiles(packageRoot)
  const findings = []

  for (const path of sourceFiles) {
    const source = await readFile(path, 'utf8')
    if (!source.includes('eslint-disable')) continue
    findings.push(...findForbiddenDisableLines(source, path).map((line) => `${relative(packageRoot, path)}:${line}`))
  }

  if (findings.length > 0) {
    process.stderr.write(
      `Forbidden ESLint disable directives found:\n${findings.map((finding) => `  ${finding}`).join('\n')}\n`
    )
    process.exitCode = 1
  }
}

main().catch((error) => {
  process.stderr.write(`Failed to check ESLint disable policy: ${String(error)}\n`)
  process.exitCode = 1
})
