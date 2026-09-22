import type { AxeResults, CrossTreeSelector, Result } from 'axe-core'
import fs from 'node:fs/promises'
import path from 'node:path'

export type A11yViolationNode = {
  targets: string[]
  html: string
  failureSummary?: string
}

export type A11yViolation = {
  ruleId: string
  impact: string | null | undefined
  description: string
  helpUrl: string
  wcagTags: string[]
  nodes: A11yViolationNode[]
}

export type A11yPageReport = {
  section: string
  name: string
  path: string
  violationCount: number
  violations: A11yViolation[]
  loadError?: string
}

export type A11yAuditReport = {
  generatedAt: string
  pageCount: number
  pagesWithViolations: number
  totalViolations: number
  pages: A11yPageReport[]
}

export type A11yPageDescriptor = Pick<A11yPageReport, 'section' | 'name' | 'path'>

const WCAG_RULE_TAG_PREFIX = 'wcag'

function formatTargetSelector(target: CrossTreeSelector): string {
  return typeof target === 'string' ? target : target.join(' ')
}

export function formatPageKey(entry: Pick<A11yPageDescriptor, 'section' | 'name'>): string {
  return `${entry.section}/${entry.name}`
}

export function toA11yViolation(violation: Result): A11yViolation {
  return {
    ruleId: violation.id,
    impact: violation.impact,
    description: violation.description,
    helpUrl: violation.helpUrl,
    wcagTags: violation.tags.filter((tag) => tag.startsWith(WCAG_RULE_TAG_PREFIX)),
    nodes: violation.nodes.map((node) => ({
      targets: node.target.map(formatTargetSelector),
      html: node.html,
      failureSummary: node.failureSummary,
    })),
  }
}

export function buildPageReport(entry: A11yPageDescriptor, axeResults: AxeResults, loadError?: string): A11yPageReport {
  const violations = axeResults.violations.map(toA11yViolation)
  return {
    section: entry.section,
    name: entry.name,
    path: entry.path,
    violationCount: violations.length,
    violations,
    ...(loadError ? { loadError } : {}),
  }
}

export function mergeAuditReport(pageReports: A11yPageReport[]): A11yAuditReport {
  const totalViolations = pageReports.reduce((sum, page) => sum + page.violationCount, 0)
  const pagesWithViolations = pageReports.filter((page) => page.violationCount > 0).length

  return {
    generatedAt: new Date().toISOString(),
    pageCount: pageReports.length,
    pagesWithViolations,
    totalViolations,
    pages: pageReports,
  }
}

export function formatAuditSummary(report: A11yAuditReport): string {
  const lines = [
    'A11y audit summary',
    `  pages scanned: ${report.pageCount}`,
    `  pages with violations: ${report.pagesWithViolations}`,
    `  total violations: ${report.totalViolations}`,
  ]

  for (const page of report.pages) {
    if (page.loadError) {
      lines.push(`  ${formatPageKey(page)} (${page.path}): page load warning — ${page.loadError}`)
    }
    if (page.violationCount === 0) continue
    lines.push(`  ${formatPageKey(page)} (${page.path}): ${page.violationCount} violation(s)`)
    for (const violation of page.violations) {
      lines.push(`    - ${violation.ruleId} [${violation.impact ?? 'unknown'}] ${violation.description}`)
      for (const node of violation.nodes) {
        lines.push(`        target: ${node.targets.join(' ')}`)
        if (node.failureSummary) {
          lines.push(`        summary: ${node.failureSummary}`)
        }
      }
    }
  }

  return lines.join('\n')
}

export async function writeAuditReport(report: A11yAuditReport): Promise<string> {
  const outputPath = path.join('test-results', 'a11y-audit-report.json')
  await fs.mkdir(path.dirname(outputPath), { recursive: true })
  await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
  return outputPath
}
