import { readFile } from 'node:fs/promises'

import type { TestInfo } from '@playwright/test'

export type XfailEntry = {
  pattern: string
  reason: string
}

/** Custom annotation type applied when a listed playwright.md test passed. */
export const XFAIL_ANNOTATION_TYPE = 'xfail'

/** Prefix of skip-annotation descriptions applied when a listed test is quarantined. */
export const XFAIL_ANNOTATION_PREFIX = 'xfail:'

export type XfailAnnotation = {
  type: string
  description?: string
}

/** Mutable test-info fields needed to quarantine after the test body runs. */
export type QuarantineTarget = {
  status?: TestInfo['status']
  annotations: XfailAnnotation[]
}

/** One finished test attempt, as seen by a Playwright reporter. */
export type XfailRunRecord = {
  status: string
  titlePath: string[]
  annotations: XfailAnnotation[]
}

export type ListedXfailPass = {
  testId: string
  reason: string
}

/**
 * Currents-style quarantine: run the test normally, then rewrite a listed failure
 * so it does not fail the suite. A listed pass is left as a pass (stale list entry).
 *
 * Listed failures are swallowed on the attempt that failed. That also prevents
 * Playwright from retrying them, which would leave an earlier failed result and
 * still fail the run.
 */
export function applyQuarantineAfterRun(testInfo: QuarantineTarget, match: XfailEntry | null): void {
  if (!match) return

  if (testInfo.status === 'passed') {
    testInfo.annotations.push({ type: XFAIL_ANNOTATION_TYPE, description: match.reason })
    return
  }

  if (testInfo.status !== 'failed' && testInfo.status !== 'timedOut') return

  testInfo.annotations.push({
    type: 'skip',
    description: `${XFAIL_ANNOTATION_PREFIX} ${match.reason}`,
  })
  testInfo.status = 'skipped'
}

export function listedXfailPass(record: XfailRunRecord): ListedXfailPass | null {
  if (record.status !== 'passed') return null
  const match = record.annotations.find((annotation) => annotation.type === XFAIL_ANNOTATION_TYPE)
  if (!match) return null
  return {
    testId: record.titlePath.filter(Boolean).join(' > '),
    reason: match.description?.trim() || 'listed in xfail list',
  }
}

export function collectListedXfailPasses(records: XfailRunRecord[]): ListedXfailPass[] {
  return records.flatMap((record) => {
    const found = listedXfailPass(record)
    return found ? [found] : []
  })
}

/** End-of-run summary lines; empty when no listed tests passed. */
export function formatListedXfailPasses(passes: ListedXfailPass[]): string[] {
  if (passes.length === 0) return []
  return [
    `xpass: ${passes.length} listed test(s) passed (remove from playwright.md):`,
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
