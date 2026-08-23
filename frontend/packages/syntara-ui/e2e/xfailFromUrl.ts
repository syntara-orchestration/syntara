import { readFile } from 'node:fs/promises'

import type { TestInfo } from '@playwright/test'

export type XfailEntry = {
  pattern: string
  reason: string
}

export type XfailMode = 'fail' | 'skip'

/** Shared Currents export. GHA sets SYNTARA_XFAIL_SOURCE to this; Konflux does not. */
export const DEFAULT_XFAIL_SOURCE =
  'https://raw.githubusercontent.com/syntara-orchestration/syntara-ci/refs/heads/main/'

export function toXfailMarkdownUrl(sourceBase: string, filename: string): string {
  return sourceBase.endsWith('/') ? `${sourceBase}${filename}` : `${sourceBase}/${filename}`
}

/**
 * Empty `SYNTARA_XFAIL_SOURCE` disables the list. Unset uses {@link DEFAULT_XFAIL_SOURCE}.
 * GHA sets the env explicitly; Konflux does not, and its pods often omit `CI`, so gating
 * on `CI` left the required UI gate running tests GHA already quarantines.
 */
export function resolveXfailSource(env: Record<string, string | undefined>): string | undefined {
  if ('SYNTARA_XFAIL_SOURCE' in env) {
    const explicit = env.SYNTARA_XFAIL_SOURCE?.trim() ?? ''
    return explicit || undefined
  }
  return DEFAULT_XFAIL_SOURCE
}

export function currentsActionsConfigured(env: Record<string, string | undefined>): boolean {
  const apiKey = env.CURRENTS_API_KEY?.trim()
  const projectId = env.CURRENTS_PROJECT_ID?.trim()
  const recordKey = env.CURRENTS_RECORD_KEY?.trim()
  return Boolean(apiKey || (projectId && recordKey))
}

/**
 * GHA has Currents credentials and uses expected-fail so quarantined tests still run.
 * Konflux does not: `test.fail()` would then fail the gate on unexpected passes of flaky tests.
 */
export function xfailMode(env: Record<string, string | undefined>): XfailMode {
  return currentsActionsConfigured(env) ? 'fail' : 'skip'
}

export function applyListedXfail(testInfo: Pick<TestInfo, 'fail' | 'skip'>, match: XfailEntry, mode: XfailMode): void {
  const message = `xfail: ${match.reason}`
  if (mode === 'skip') {
    testInfo.skip(true, message)
    return
  }
  testInfo.fail(true, message)
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

function e2eRelativePath(filePath: string): string {
  const normalized = filePath.replaceAll('\\', '/')
  const marker = '/e2e/'
  const idx = normalized.lastIndexOf(marker)
  if (idx !== -1) {
    return normalized.slice(idx + marker.length)
  }
  return normalized.slice(normalized.lastIndexOf('/') + 1)
}

function buildTestId(testInfo: TestInfo): string {
  const relPath = e2eRelativePath(testInfo.file)
  const titles = testInfo.titlePath.filter(Boolean)
  return [relPath, ...titles].join(' > ')
}

function testIdIsInFile(testId: string, filePrefix: string): boolean {
  const normalized = testId.replaceAll('\\', '/')
  const prefix = filePrefix.replaceAll('\\', '/')
  const first = normalized.split(' > ')[0] ?? ''
  return (
    first === prefix ||
    first.endsWith(`/${prefix}`) ||
    normalized.startsWith(`${prefix} > `) ||
    normalized.startsWith(`${prefix}/`)
  )
}

export function matchPattern(testId: string, pattern: string): boolean {
  const colonIdx = pattern.indexOf(': ')
  if (colonIdx !== -1) {
    const filePrefix = pattern.slice(0, colonIdx)
    if (filePrefix.includes('/') || filePrefix.endsWith('.ts') || filePrefix.endsWith('.js')) {
      const titlePart = pattern.slice(colonIdx + 2)
      if (!testIdIsInFile(testId, filePrefix)) {
        return false
      }
      if (!titlePart) {
        return true
      }
      return testId.endsWith(` > ${titlePart}`) || testId === `${filePrefix} > ${titlePart}`
    }
  }

  if (pattern.includes(' > ')) {
    return testId === pattern || testId.endsWith(` > ${pattern}`)
  }
  return testId.startsWith(pattern) || testIdIsInFile(testId, pattern)
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
