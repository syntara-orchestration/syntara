import type { FullResult, Reporter, TestCase, TestResult } from '@playwright/test/reporter'

import {
  collectUnexpectedXfailPasses,
  formatUnexpectedXfailPasses,
  softenFailedRunForXfailPasses,
  type XfailRunRecord,
} from './xfailFromUrl'

function toRecord(test: TestCase, result: TestResult): XfailRunRecord {
  return {
    expectedStatus: test.expectedStatus,
    status: result.status ?? '',
    titlePath: test.titlePath(),
    annotations: [...test.annotations, ...result.annotations],
  }
}

/**
 * Prints listed xfail tests that passed, and keeps the run green when those are
 * the only unexpected results (pytest-style non-strict xfail).
 */
export default class XfailReporter implements Reporter {
  private readonly lastByTestId = new Map<string, { test: TestCase; result: TestResult }>()

  printsToStdio(): boolean {
    return true
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    this.lastByTestId.set(test.id, { test, result })
  }

  onEnd(result: FullResult): Promise<{ status?: FullResult['status'] } | undefined> {
    const records = [...this.lastByTestId.values()].map(({ test, result: testResult }) => toRecord(test, testResult))
    for (const line of formatUnexpectedXfailPasses(collectUnexpectedXfailPasses(records))) {
      console.log(line)
    }
    const status = softenFailedRunForXfailPasses(result.status, records)
    return Promise.resolve(status ? { status } : undefined)
  }
}
