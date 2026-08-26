#!/usr/bin/env node
/**
 * Post-process Playwright test results to handle quarantined test failures.
 *
 * Reads JSON results from Playwright and determines if the build should fail:
 * - All failures quarantined → exit 0 (build passes)
 * - Any non-quarantined failure → exit 1 (build fails)
 * - All tests passed → exit 0
 *
 * Usage: npx playwright test || npx tsx e2e/check-quarantine-failures.ts $?
 */

import { readFile } from 'node:fs/promises'
import { exit } from 'node:process'

type TestResult = {
  status: string
  annotations?: Array<{ type: string; description?: string }>
}

type TestCase = {
  title: string
  results: TestResult[]
}

type Suite = {
  title: string
  suites?: Suite[]
  specs?: TestCase[]
}

type PlaywrightResults = {
  suites: Suite[]
}

type FailedTest = {
  title: string
  quarantined: boolean
  reason?: string
}

function* walkTests(suite: Suite): Generator<{ path: string[]; test: TestCase }> {
  const path = suite.title ? [suite.title] : []

  if (suite.specs) {
    for (const spec of suite.specs) {
      yield { path, test: spec }
    }
  }

  if (suite.suites) {
    for (const child of suite.suites) {
      yield* walkTests(child)
    }
  }
}

function collectFailures(results: PlaywrightResults): {
  quarantinedCount: number
  nonQuarantinedCount: number
  tests: FailedTest[]
} {
  const tests: FailedTest[] = []
  let quarantinedCount = 0
  let nonQuarantinedCount = 0

  for (const suite of results.suites) {
    for (const { path, test } of walkTests(suite)) {
      for (const result of test.results) {
        const isFailed = result.status === 'failed' || result.status === 'timedOut'
        if (!isFailed) continue

        const isQuarantined = result.annotations?.some((a) => a.type === 'quarantined') ?? false
        const reason = result.annotations?.find((a) => a.type === 'quarantined')?.description
        const fullTitle = [...path, test.title].filter(Boolean).join(' > ')

        tests.push({ title: fullTitle, quarantined: isQuarantined, reason })

        if (isQuarantined) {
          quarantinedCount++
        } else {
          nonQuarantinedCount++
        }
      }
    }
  }

  return { quarantinedCount, nonQuarantinedCount, tests }
}

function reportResults(failures: ReturnType<typeof collectFailures>): void {
  const { quarantinedCount, nonQuarantinedCount, tests } = failures

  if (quarantinedCount > 0) {
    process.stdout.write(`\n🟡 ${quarantinedCount} quarantined test failure(s) (soft fail):\n`)
    for (const test of tests.filter((t) => t.quarantined)) {
      process.stdout.write(`  ⚠️  ${test.title}\n`)
      if (test.reason) {
        process.stdout.write(`     Reason: ${test.reason}\n`)
      }
    }
  }

  if (nonQuarantinedCount > 0) {
    process.stdout.write(`\n❌ ${nonQuarantinedCount} non-quarantined test failure(s):\n`)
    for (const test of tests.filter((t) => !t.quarantined)) {
      process.stdout.write(`  ✗ ${test.title}\n`)
    }
    process.stdout.write('\n❌ Build failed due to non-quarantined test failures\n')
  } else {
    process.stdout.write(`\n✅ All ${quarantinedCount} failure(s) are quarantined. Build passes.\n`)
  }
}

async function main(playwrightExitCode: number): Promise<void> {
  if (playwrightExitCode === 0) {
    process.stdout.write('✅ All tests passed\n')
    exit(0)
  }

  const resultsPath = 'test-results/results.json'
  let results: PlaywrightResults
  try {
    const content = await readFile(resultsPath, 'utf-8')
    results = JSON.parse(content) as PlaywrightResults
  } catch (error) {
    process.stderr.write(`❌ Failed to read results from ${resultsPath}: ${String(error)}\n`)
    exit(playwrightExitCode)
  }

  const failures = collectFailures(results)
  reportResults(failures)

  if (failures.nonQuarantinedCount > 0) {
    exit(1)
  } else {
    exit(0)
  }
}

const playwrightExitCode = Number.parseInt(process.argv[2] ?? '0', 10)
main(playwrightExitCode).catch((error) => {
  process.stderr.write(`Unexpected error: ${String(error)}\n`)
  exit(1)
})
