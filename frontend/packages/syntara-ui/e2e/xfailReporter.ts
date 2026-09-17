import type { Reporter, TestCase, TestResult } from '@playwright/test/reporter'

import { collectListedXfailPasses, formatListedXfailPasses, type XfailRunRecord } from './xfailFromUrl'

function toRecord(test: TestCase, result: TestResult): XfailRunRecord {
  return {
    status: result.status ?? '',
    titlePath: [...test.titlePath()],
    annotations: [...(test.annotations ?? []), ...(result.annotations ?? [])],
  }
}

/**
 * Prints listed playwright.md tests that passed so they can be removed from the
 * quarantine list. Exit status is unchanged: listed failures are already
 * rewritten to skipped by `_xfailCheck`.
 */
export default class XfailReporter implements Reporter {
  private readonly lastByTestId = new Map<string, XfailRunRecord>()

  printsToStdio(): boolean {
    return false
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    this.lastByTestId.set(test.id, toRecord(test, result))
  }

  onEnd(): void {
    for (const line of formatListedXfailPasses(collectListedXfailPasses([...this.lastByTestId.values()]))) {
      console.log(line)
    }
  }
}
