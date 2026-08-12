import type { TestInfo } from '@playwright/test'

export interface XfailEntry {
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

export async function fetchXfailEntries(url: string): Promise<XfailEntry[]> {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(30_000) })
    if (!response.ok) {
      console.warn(`xfail: failed to fetch ${url}: ${response.status} ${response.statusText}`)
      return []
    }
    const content = await response.text()
    return parseXfailEntries(content)
  } catch (error) {
    console.warn(`xfail: failed to fetch ${url}:`, error)
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
