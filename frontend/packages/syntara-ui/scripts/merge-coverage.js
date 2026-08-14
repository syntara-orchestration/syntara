#!/usr/bin/env node

import { execFileSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from 'node:fs'
import { join, resolve } from 'node:path'

const COVERAGE_ARTIFACTS_DIR = resolve(process.cwd(), process.env.COVERAGE_ARTIFACTS_DIR ?? 'coverage-artifacts')
const NYC_OUTPUT_DIR = resolve(process.cwd(), '.nyc_output')
const COVERAGE_DIR = resolve(process.cwd(), 'coverage')

function collectCoverageFiles(directory) {
  const entries = readdirSync(directory, { withFileTypes: true })
  const files = []

  for (const entry of entries) {
    const fullPath = join(directory, entry.name)

    if (entry.isDirectory()) {
      files.push(...collectCoverageFiles(fullPath))
      continue
    }

    if (entry.isFile() && entry.name === 'coverage-final.json') {
      files.push(fullPath)
    }
  }

  return files
}

if (!existsSync(COVERAGE_ARTIFACTS_DIR)) {
  console.error(`Coverage artifacts directory not found: ${COVERAGE_ARTIFACTS_DIR}`)
  process.exit(1)
}

const coverageFiles = collectCoverageFiles(COVERAGE_ARTIFACTS_DIR)

if (coverageFiles.length === 0) {
  console.error(`No coverage-final.json files found in ${COVERAGE_ARTIFACTS_DIR}`)
  process.exit(1)
}

rmSync(NYC_OUTPUT_DIR, { recursive: true, force: true })
rmSync(COVERAGE_DIR, { recursive: true, force: true })
mkdirSync(NYC_OUTPUT_DIR, { recursive: true })

for (const [index, coverageFile] of coverageFiles.entries()) {
  cpSync(coverageFile, join(NYC_OUTPUT_DIR, `shard-${index + 1}.json`))
}

const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'

execFileSync(npmCommand, ['run', 'test:coverage:report', '--silent'], { stdio: 'inherit' })

console.log(`Merged ${coverageFiles.length} coverage shard(s) into ${COVERAGE_DIR}`)

const COVERAGE_THRESHOLD = '85'

execFileSync(
  npmCommand,
  ['exec', '--', 'nyc', 'check-coverage', '--temp-dir', NYC_OUTPUT_DIR, '--statements', COVERAGE_THRESHOLD],
  { stdio: 'inherit' }
)
