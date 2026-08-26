import type { Reporter, TestCase, TestResult } from '@playwright/test/reporter'

/**
 * Quarantine Reporter
 *
 * Logs quarantined test status during Playwright execution.
 * Tests annotated with `{ type: 'quarantined' }` are tracked separately.
 * Exit code handling is delegated to check-quarantine-failures.ts.
 */
export class QuarantineReporter implements Reporter {
  private quarantinedFailures: Array<{ test: TestCase; result: TestResult }> = []
  private nonQuarantinedFailures: Array<{ test: TestCase; result: TestResult }> = []
  private quarantinedPasses: Array<{ test: TestCase; result: TestResult }> = []

  onTestEnd(test: TestCase, result: TestResult): void {
    const isQuarantined = test.annotations.some((a) => a.type === 'quarantined')

    if (result.status === 'failed' || result.status === 'timedOut') {
      if (isQuarantined) {
        this.quarantinedFailures.push({ test, result })
      } else {
        this.nonQuarantinedFailures.push({ test, result })
      }
    } else if (result.status === 'passed' && isQuarantined) {
      this.quarantinedPasses.push({ test, result })
    }
  }

  onEnd(): void {
    if (this.quarantinedFailures.length > 0) {
      process.stdout.write('\n🟡 Quarantined test failures (soft fail):\n')
      for (const { test } of this.quarantinedFailures) {
        const annotation = test.annotations.find((a) => a.type === 'quarantined')
        const reason = annotation?.description ?? 'listed in quarantine'
        process.stdout.write(`  ⚠️  ${test.titlePath().join(' > ')}\n`)
        process.stdout.write(`     Reason: ${reason}\n`)
      }
    }

    if (this.quarantinedPasses.length > 0) {
      process.stdout.write('\n✅ Quarantined tests that now pass (potentially fixed):\n')
      for (const { test } of this.quarantinedPasses) {
        process.stdout.write(`  ✓ ${test.titlePath().join(' > ')}\n`)
      }
    }

    if (this.nonQuarantinedFailures.length > 0) {
      process.stdout.write(`\n❌ ${this.nonQuarantinedFailures.length} non-quarantined test(s) failed\n`)
    } else if (this.quarantinedFailures.length > 0) {
      const count = this.quarantinedFailures.length
      const suffix = count === 1 ? '' : 's'
      process.stdout.write(`\n✅ All failures are quarantined (${count} soft fail${suffix})\n`)
    }
  }

  printsToStdio(): boolean {
    return false
  }
}
