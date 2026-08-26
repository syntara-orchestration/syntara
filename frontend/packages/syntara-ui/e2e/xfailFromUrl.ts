import { readFile } from 'node:fs/promises'

import type { TestInfo } from '@playwright/test'

export type XfailEntry = {
  pattern: string
  reason: string
}

/** Prefix of the `testInfo.fail()` description applied by `_xfailCheck`. */
export const XFAIL_ANNOTATION_PREFIX = 'xfail:'

export function xfailFailDescription(reason: string): string {
  return `${XFAIL_ANNOTATION_PREFIX} ${reason}`
}

export type XfailAnnotation = {
  type: string
  description?: string
}

/** One finished test attempt, as seen by a Playwright reporter. */
export type XfailRunRecord = {
  expectedStatus: string
  status: string
  titlePath: string[]
  annotations: XfailAnnotation[]
}

export type UnexpectedXfailPass = {
  testId: string
  reason: string
}

export function xfailReasonFromAnnotations(annotations: XfailAnnotation[]): string | null {
  const match = annotations.find(
    (annotation) => annotation.type === 'fail' && annotation.description?.startsWith(XFAIL_ANNOTATION_PREFIX)
  )
  if (!match?.description) return null
  return match.description.slice(XFAIL_ANNOTATION_PREFIX.length).trim() || 'listed in xfail list'
}

/**
 * A listed xfail test that passed (Playwright "Expected to fail, but passed").
 * Ignores `test.fail()` / Currents quarantine that do not use our annotation prefix.
 */
export function unexpectedXfailPass(record: XfailRunRecord): UnexpectedXfailPass | null {
  if (record.expectedStatus !== 'failed' || record.status !== 'passed') return null
  const reason = xfailReasonFromAnnotations(record.annotations)
  if (reason === null) return null
  return { testId: record.titlePath.filter(Boolean).join(' > '), reason }
}

export function collectUnexpectedXfailPasses(records: XfailRunRecord[]): UnexpectedXfailPass[] {
  return records.flatMap((record) => {
    const found = unexpectedXfailPass(record)
    return found ? [found] : []
  })
}

/**
 * True when some test failed for a reason other than a listed xfail passing.
 * An xfail that did fail (or time out) is expected and not blocking.
 */
export function hasNonXfailFailure(records: XfailRunRecord[]): boolean {
  return records.some((record) => {
    if (record.status === 'skipped') return false
    if (record.expectedStatus === 'passed' && record.status === 'passed') return false
    if (record.expectedStatus === 'failed' && (record.status === 'failed' || record.status === 'timedOut')) {
      return false
    }
    if (unexpectedXfailPass(record)) return false
    return true
  })
}

/**
 * pytest-like non-strict xfail: listed tests that pass must not fail the run.
 * Playwright's `testInfo.fail(true)` would otherwise exit non-zero; reporters may
 * override that via `onEnd`.
 */
export function softenFailedRunForXfailPasses(runStatus: string, records: XfailRunRecord[]): 'passed' | undefined {
  if (runStatus !== 'failed') return undefined
  if (collectUnexpectedXfailPasses(records).length === 0) return undefined
  if (hasNonXfailFailure(records)) return undefined
  return 'passed'
}

/** End-of-run summary lines; empty when nothing unexpectedly passed. */
export function formatUnexpectedXfailPasses(passes: UnexpectedXfailPass[]): string[] {
  if (passes.length === 0) return []
  return [
    `xfail: ${passes.length} listed test(s) passed (remove from playwright.md):`,
    ...passes.map(({ testId, reason }) => `  - ${testId} — ${reason.replace(/\n/g, ' ')}`),
  ]
}

const HEADING_RE = /^#\s+(.+)$/

export function parseXfailEntries(content: string): XfailEntry[] {
  const entries: XfailEntry[] = []
  let currentPattern: string | null = null
  const reasonLines: string[] = []

  function flush(): void {
    if (currentPattern !== null) {
      const reason = reasonLines.join('\n').trim() || 'listed in xfail list'
      entries.push({ pattern: currentPattern, reason })
    }
  }

  for (const line of content.split('\n')) {
    const match = HEADING_RE.exec(line.trim())
    if (match) {
      flush()
      currentPattern = match[1].trim()
      reasonLines.length = 0
    } else if (currentPattern !== null) {
      const stripped = line.trim()
      if (stripped) {
        reasonLines.push(stripped)
      }
    }
  }
  flush()
  return entries
}

function isFilePath(source: string): boolean {
  return source.startsWith('/') || source.startsWith('./') || source.startsWith('../')
}

/**
 * Resolve the xfail Markdown URL/path from SYNTARA_XFAIL_SOURCE, or null if unset.
 * The env var is a base URL/dir; the Playwright list lives at `<base>/playwright.md`.
 */
export function xfailSourceFromEnv(env: Record<string, string | undefined> = process.env): string | null {
  const base = env['SYNTARA_XFAIL_SOURCE']
  if (!base) return null
  return base.endsWith('/') ? `${base}playwright.md` : `${base}/playwright.md`
}

/** Human-readable summary lines for the active xfail rules, for printing at the start of a run. */
export function formatXfailRules(entries: XfailEntry[], source: string): string[] {
  if (entries.length === 0) {
    return [`xfail: no rules loaded from ${source}`]
  }
  return [
    `xfail: ${entries.length} rule(s) from ${source}:`,
    ...entries.map(({ pattern, reason }) => `  - ${pattern} — ${reason.replace(/\n/g, ' ')}`),
  ]
}

export async function loadXfailEntries(source: string): Promise<XfailEntry[]> {
  try {
    let content: string
    if (isFilePath(source)) {
      content = await readFile(source, 'utf-8')
    } else {
      const nodeFetch = globalThis.fetch
      const response = await nodeFetch(source, { signal: AbortSignal.timeout(30_000) })
      if (!response.ok) {
        process.stderr.write(`xfail: failed to fetch ${source}: ${response.status} ${response.statusText}\n`)
        return []
      }
      content = await response.text()
    }
    return parseXfailEntries(content)
  } catch (error) {
    process.stderr.write(`xfail: failed to load ${source}: ${String(error)}\n`)
    return []
  }
}

export function buildTestId(testInfo: Pick<TestInfo, 'titlePath'>): string {
  // testInfo.titlePath already starts with the testDir-relative spec path, so
  // it is the full id on its own: [relPath, ...describeTitles, testTitle].
  // Do NOT prepend testInfo.file — that duplicates the spec path in the id
  // (e.g. "a.spec.ts > a.spec.ts > test") and breaks exact-match patterns.
  return testInfo.titlePath.filter(Boolean).join(' > ')
}

export function matchPattern(testId: string, pattern: string): boolean {
  const colonIdx = pattern.indexOf(': ')
  if (colonIdx !== -1) {
    const filePrefix = pattern.slice(0, colonIdx)
    if (filePrefix.includes('/') || filePrefix.endsWith('.ts') || filePrefix.endsWith('.js')) {
      const titlePart = pattern.slice(colonIdx + 2)
      if (!titlePart) {
        return testId.startsWith(filePrefix)
      }
      const fullPattern = `${filePrefix} > ${titlePart}`
      return testId === fullPattern || (testId.startsWith(`${filePrefix} > `) && testId.endsWith(` > ${titlePart}`))
    }
  }

  if (pattern.includes(' > ')) {
    return testId === pattern || testId.endsWith(` > ${pattern}`)
  }
  return testId.startsWith(pattern)
}

export function matchesXfail(testInfo: TestInfo, entries: XfailEntry[]): XfailEntry | null {
  if (entries.length === 0) return null
  const testId = buildTestId(testInfo)
  for (const entry of entries) {
    if (matchPattern(testId, entry.pattern)) {
      return entry
    }
  }
  return null
}
