import { readFile } from 'node:fs/promises'

import type { TestInfo } from '@playwright/test'

export type XfailEntry = {
  pattern: string
  reason: string
}

const HEADING_RE = /^#\s+(.+)$/

export function parseXfailEntries(content: string): XfailEntry[] {
  const entries: XfailEntry[] = []
  let currentPattern: string | null = null
  const reasonLines: string[] = []

  function flush(): void {
    if (currentPattern !== null) {
      const reason = reasonLines.join(' ').trim() || 'listed in xfail list'
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

function buildTestId(testInfo: TestInfo): string {
  const testDir = testInfo.project.testDir
  let relPath = testInfo.file
  if (testDir && relPath.startsWith(testDir)) {
    relPath = relPath.slice(testDir.length).replace(/^[/\\]/, '')
  }
  const titles = testInfo.titlePath.filter(Boolean)
  return [relPath, ...titles].join(' > ')
}

export function matchesXfail(
  testInfo: TestInfo,
  entries: XfailEntry[]
): XfailEntry | null {
  if (entries.length === 0) return null
  const testId = buildTestId(testInfo)
  for (const entry of entries) {
    if (entry.pattern.includes(' > ')) {
      if (testId === entry.pattern || testId.endsWith(entry.pattern)) {
        return entry
      }
    } else {
      if (testId.startsWith(entry.pattern)) {
        return entry
      }
    }
  }
  return null
}
