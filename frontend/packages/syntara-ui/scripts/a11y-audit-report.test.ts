import { describe, expect, it } from 'vitest'

import { formatAuditSummary, mergeAuditReport, toA11yViolation } from './a11y-audit-report'

describe('a11y-audit-report', () => {
  it('maps axe violations to structured report entries', () => {
    const violation = toA11yViolation({
      id: 'color-contrast',
      impact: 'serious',
      tags: ['wcag2aa', 'wcag21aa', 'cat.color'],
      description: 'Elements must have sufficient color contrast',
      help: 'Ensure contrast',
      helpUrl: 'https://dequeuniversity.com/rules/axe/4.10/color-contrast',
      nodes: [
        {
          html: '<button>Save</button>',
          target: ['button'],
          failureSummary: 'Fix contrast',
          any: [],
          all: [],
          none: [],
        },
      ],
    })

    expect(violation).toEqual({
      ruleId: 'color-contrast',
      impact: 'serious',
      description: 'Elements must have sufficient color contrast',
      helpUrl: 'https://dequeuniversity.com/rules/axe/4.10/color-contrast',
      wcagTags: ['wcag2aa', 'wcag21aa'],
      nodes: [
        {
          html: '<button>Save</button>',
          targets: ['button'],
          failureSummary: 'Fix contrast',
        },
      ],
    })
  })

  it('merges page reports and formats a summary', () => {
    const report = mergeAuditReport([
      {
        section: 'workflows',
        name: 'workflows-list',
        path: '/workflows',
        violationCount: 1,
        violations: [
          {
            ruleId: 'color-contrast',
            impact: 'serious',
            description: 'Elements must have sufficient color contrast',
            helpUrl: 'https://example.com',
            wcagTags: ['wcag2aa'],
            nodes: [{ targets: ['button'], html: '<button>Save</button>' }],
          },
        ],
      },
      {
        section: 'login',
        name: 'login-default',
        path: '/',
        violationCount: 0,
        violations: [],
      },
    ])

    expect(report.pageCount).toBe(2)
    expect(report.pagesWithViolations).toBe(1)
    expect(report.totalViolations).toBe(1)
    expect(formatAuditSummary(report)).toContain('workflows/workflows-list (/workflows): 1 violation(s)')
    expect(formatAuditSummary(report)).toContain('color-contrast [serious]')
    expect(formatAuditSummary(report)).toContain('target: button')
  })
})
