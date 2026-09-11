import { describe, expect, it } from 'vitest'

import { formatScopeLine, resolveScope } from './scope-visual-regression'

describe('resolveScope', () => {
  it('returns NONE when no VR-relevant files changed', () => {
    expect(resolveScope(['backend/src/syntara/main.py', 'README.md'])).toEqual({
      full: false,
      sections: [],
    })
    expect(formatScopeLine(resolveScope(['backend/src/syntara/main.py']))).toBe('SCOPE=NONE')
  })

  it('scopes an isolated route folder to that section', () => {
    const result = resolveScope(['frontend/packages/syntara-ui/src/routes/workflows/WorkflowsList.tsx'])
    expect(result).toEqual({ full: false, sections: ['workflows'] })
    expect(formatScopeLine(result)).toBe('SCOPE=(?:^|\\s)(workflows)/')
  })

  it('forces FULL for syntara-mock-api changes alone', () => {
    expect(resolveScope(['frontend/packages/syntara-mock-api/src/handlers.ts'])).toEqual({ full: true })
    expect(formatScopeLine(resolveScope(['frontend/packages/syntara-mock-api/src/handlers.ts']))).toBe('SCOPE=FULL')
  })

  it('forces FULL when mock-api changes accompany a scoped route file', () => {
    expect(
      resolveScope([
        'frontend/packages/syntara-mock-api/src/handlers.ts',
        'frontend/packages/syntara-ui/src/routes/workflows/WorkflowsList.tsx',
      ])
    ).toEqual({ full: true })
  })

  it('forces FULL for syntara-contracts changes', () => {
    expect(resolveScope(['frontend/packages/syntara-contracts/src/schemas.ts'])).toEqual({ full: true })
  })

  it('forces FULL for unmatched shared syntara-ui files', () => {
    expect(resolveScope(['frontend/packages/syntara-ui/src/components/Button.tsx'])).toEqual({ full: true })
    expect(resolveScope(['frontend/packages/syntara-ui/e2e/visual-regression/page-registry.ts'])).toEqual({
      full: true,
    })
  })

  it('unions sections when multiple isolated folders change', () => {
    const result = resolveScope([
      'frontend/packages/syntara-ui/src/routes/workflows/WorkflowsList.tsx',
      'frontend/packages/syntara-ui/src/routes/approvals/ApprovalsList.tsx',
    ])
    expect(result.full).toBe(false)
    if (!result.full) {
      expect(result.sections.sort()).toEqual(['approvals', 'workflows'])
    }
  })
})
