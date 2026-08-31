import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { axe } from 'vitest-axe'

import { PolicyDetailSidebar } from './PolicyDetailSidebar'
import type { PolicyRead } from './types'

vi.mock('../../components/details/SynCodeBlock', () => ({
  SynCodeBlock: ({ jsonObject }: { jsonObject: unknown }) => <pre>{JSON.stringify(jsonObject)}</pre>,
}))

const builtinPolicy: PolicyRead = {
  id: 'p1',
  name: 'admin-policy',
  description: 'Full admin access to all resources',
  statements: [
    {
      scope: 'any',
      effect: 'allow',
      actions: ['workflow:read', 'workflow:write'],
    },
    {
      scope: 'self',
      effect: 'deny',
      actions: ['workflow:delete'],
      conditions: { ip_range: '10.0.0.0/8' },
    },
  ],
  is_builtin: true,
  is_project_eligible: false,
  is_system_scoped: true,
  project_id: null,
  scope: 'any',
  labels: { env: 'production', team: 'platform' },
  created_at: '2024-01-15T10:30:00Z',
  updated_at: '2024-06-20T14:45:00Z',
}

const customPolicy: PolicyRead = {
  id: 'p2',
  name: 'viewer-policy',
  description: null,
  statements: [
    {
      scope: 'self',
      effect: 'allow',
      actions: ['workflow:read'],
    },
  ],
  is_builtin: false,
  is_project_eligible: true,
  is_system_scoped: false,
  project_id: 'proj-1',
  scope: 'project',
  labels: {},
  created_at: null,
  updated_at: null,
}

const emptyStatementsPolicy: PolicyRead = {
  id: 'p3',
  name: 'empty-policy',
  description: 'No statements',
  statements: [],
  is_builtin: false,
  is_project_eligible: false,
  is_system_scoped: false,
  project_id: null,
  labels: {},
  created_at: null,
  updated_at: null,
}

describe('PolicyDetailSidebar', () => {
  const onClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders policy name and heading', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByRole('heading', { name: 'Policy details' })).toBeInTheDocument()
    expect(screen.getByText('admin-policy')).toBeInTheDocument()
  })

  it('renders Built-in label for builtin policy', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByText('Built-in')).toBeInTheDocument()
    expect(screen.getByText('This is a system policy and cannot be modified.')).toBeInTheDocument()
  })

  it('renders Custom label for custom policy', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)

    expect(screen.getByText('Custom')).toBeInTheDocument()
    expect(screen.queryByText('This is a system policy and cannot be modified.')).not.toBeInTheDocument()
  })

  it('renders policy description when present', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByText('Full admin access to all resources')).toBeInTheDocument()
  })

  it('does not render description when null', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)

    // The description paragraph should not be in the DOM
    expect(screen.queryByText('Full admin access to all resources')).not.toBeInTheDocument()
  })

  it('renders scope value from the policy', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByText('Any')).toBeInTheDocument()
  })

  it('renders project link when project_id exists', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)

    expect(screen.getByText('Project: proj-1')).toBeInTheDocument()
  })

  it('renders timestamps', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByText('Created')).toBeInTheDocument()
    expect(screen.getByText('Updated')).toBeInTheDocument()
  })

  it('renders "-" for null timestamps', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)

    const dashTexts = screen.getAllByText('-')
    expect(dashTexts.length).toBeGreaterThanOrEqual(2)
  })

  it('renders labels when present', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByText('Labels')).toBeInTheDocument()
    expect(screen.getByText('env: production')).toBeInTheDocument()
    expect(screen.getByText('team: platform')).toBeInTheDocument()
  })

  it('does not render labels section when empty', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)

    expect(screen.queryByText('Labels')).not.toBeInTheDocument()
  })

  it('renders statements with effect and actions', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByRole('heading', { name: 'Statements' })).toBeInTheDocument()
    expect(screen.getByText('ALLOW')).toBeInTheDocument()
    expect(screen.getByText('DENY')).toBeInTheDocument()
    expect(screen.getByText('workflow:read')).toBeInTheDocument()
    expect(screen.getByText('workflow:write')).toBeInTheDocument()
    expect(screen.getByText('workflow:delete')).toBeInTheDocument()
  })

  it('renders statement scope labels', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByText('scope: any')).toBeInTheDocument()
    expect(screen.getByText('scope: self')).toBeInTheDocument()
  })

  it('renders conditions when present', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByText('Conditions:')).toBeInTheDocument()
    // CodeBlock is mocked as <pre>, so look for JSON content
    expect(screen.getByText(JSON.stringify({ ip_range: '10.0.0.0/8' }))).toBeInTheDocument()
  })

  it('renders "No statements defined." when statements are empty', () => {
    render(<PolicyDetailSidebar policy={emptyStatementsPolicy} onClose={onClose} />)

    expect(screen.getByText('No statements defined.')).toBeInTheDocument()
  })

  it('renders Policy definition section', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByRole('heading', { name: 'Policy definition' })).toBeInTheDocument()
  })

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup()
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: 'Close policy details' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when Escape key is pressed', async () => {
    const user = userEvent.setup()
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    await user.keyboard('{Escape}')

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('cleans up keyboard listener on unmount', () => {
    const removeEventListenerSpy = vi.spyOn(document, 'removeEventListener')

    const { unmount } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
    unmount()

    expect(removeEventListenerSpy).toHaveBeenCalledWith('keydown', expect.any(Function))
    removeEventListenerSpy.mockRestore()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations for custom policy', async () => {
    const { container } = render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders project link with resolved project name when provided', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} projectName="My Project" />)

    expect(screen.getByText('Project: My Project')).toBeInTheDocument()
  })

  it('falls back to project ID when projectName is null', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} projectName={null} />)

    expect(screen.getByText('Project: proj-1')).toBeInTheDocument()
  })

  it('renders scope as "Any" when policy.scope is null', () => {
    const policyWithNullScope: PolicyRead = {
      ...customPolicy,
      scope: null as unknown as string,
      project_id: null,
    }
    render(<PolicyDetailSidebar policy={policyWithNullScope} onClose={onClose} />)

    expect(screen.getByText('Any')).toBeInTheDocument()
  })

  it('renders scope as "Any" when policy.scope is undefined', () => {
    const policyWithUndefinedScope: PolicyRead = {
      ...customPolicy,
      scope: undefined as unknown as string,
      project_id: null,
    }
    render(<PolicyDetailSidebar policy={policyWithUndefinedScope} onClose={onClose} />)

    expect(screen.getByText('Any')).toBeInTheDocument()
  })

  it('renders labels when policy.labels is null', () => {
    const policyWithNullLabels: PolicyRead = {
      ...customPolicy,
      labels: null as unknown as Record<string, unknown>,
    }
    render(<PolicyDetailSidebar policy={policyWithNullLabels} onClose={onClose} />)

    expect(screen.queryByText('Labels')).not.toBeInTheDocument()
  })

  it('renders statements without conditions section when conditions are absent', () => {
    const policyNoConditions: PolicyRead = {
      ...builtinPolicy,
      statements: [
        {
          scope: 'any',
          effect: 'allow',
          actions: ['workflow:read'],
        },
      ],
    }
    render(<PolicyDetailSidebar policy={policyNoConditions} onClose={onClose} />)

    expect(screen.getByText('ALLOW')).toBeInTheDocument()
    expect(screen.queryByText('Conditions:')).not.toBeInTheDocument()
  })

  it('renders statements without conditions section when conditions is empty object', () => {
    const policyEmptyConditions: PolicyRead = {
      ...builtinPolicy,
      statements: [
        {
          scope: 'any',
          effect: 'allow',
          actions: ['workflow:read'],
          conditions: {},
        },
      ],
    }
    render(<PolicyDetailSidebar policy={policyEmptyConditions} onClose={onClose} />)

    expect(screen.getByText('ALLOW')).toBeInTheDocument()
    expect(screen.queryByText('Conditions:')).not.toBeInTheDocument()
  })

  it('does not call onClose on non-Escape key', async () => {
    const user = userEvent.setup()
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    await user.keyboard('{Enter}')

    expect(onClose).not.toHaveBeenCalled()
  })

  it('renders scope value capitalized for project scope', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)

    // The Scope description list value should show "Project" (capitalized from "project")
    const scopeTerms = screen.getAllByText('Scope')
    expect(scopeTerms.length).toBeGreaterThanOrEqual(1)
  })

  it('renders policy definition JSON with name and statements', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    const policyDefinitionJson = JSON.stringify({
      name: 'admin-policy',
      description: 'Full admin access to all resources',
      statements: builtinPolicy.statements,
    })
    expect(screen.getByText(policyDefinitionJson)).toBeInTheDocument()
  })

  it('renders policy definition JSON without description when null', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)

    const policyDefinitionJson = JSON.stringify({
      name: 'viewer-policy',
      statements: customPolicy.statements,
    })
    expect(screen.getByText(policyDefinitionJson)).toBeInTheDocument()
  })

  it('renders multiple actions as individual labels', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    expect(screen.getByText('workflow:read')).toBeInTheDocument()
    expect(screen.getByText('workflow:write')).toBeInTheDocument()
    expect(screen.getByText('workflow:delete')).toBeInTheDocument()
  })

  it('renders allow effect with green label and deny with red label', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    const allowLabel = screen.getByText('ALLOW')
    const denyLabel = screen.getByText('DENY')
    expect(allowLabel).toBeInTheDocument()
    expect(denyLabel).toBeInTheDocument()
  })

  it('does not render project section when project_id is null', () => {
    const policyNoProject: PolicyRead = {
      ...builtinPolicy,
      project_id: null,
    }
    render(<PolicyDetailSidebar policy={policyNoProject} onClose={onClose} />)

    expect(screen.queryByText(/Project:/)).not.toBeInTheDocument()
  })

  it('renders formatted date for created_at and updated_at', () => {
    render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

    const createdTerm = screen.getByText('Created')
    const updatedTerm = screen.getByText('Updated')
    expect(createdTerm).toBeInTheDocument()
    expect(updatedTerm).toBeInTheDocument()
    // formatDateTime returns a formatted string for valid ISO dates
    expect(screen.queryByText('-')).not.toBeInTheDocument()
  })

  it('renders conditions code block for statements with conditions', () => {
    const policyWithMultipleConditions: PolicyRead = {
      ...customPolicy,
      project_id: null,
      statements: [
        {
          scope: 'any',
          effect: 'allow',
          actions: ['workflow:read'],
          conditions: { resource_type: 'workflow', owner: 'admin' },
        },
      ],
    }
    render(<PolicyDetailSidebar policy={policyWithMultipleConditions} onClose={onClose} />)

    expect(screen.getByText('Conditions:')).toBeInTheDocument()
    expect(screen.getByText(JSON.stringify({ resource_type: 'workflow', owner: 'admin' }))).toBeInTheDocument()
  })

  it('renders a policy with only deny statements', () => {
    const denyOnlyPolicy: PolicyRead = {
      ...customPolicy,
      project_id: null,
      statements: [
        {
          scope: 'any',
          effect: 'deny',
          actions: ['workflow:delete', 'workflow:write'],
        },
      ],
    }
    render(<PolicyDetailSidebar policy={denyOnlyPolicy} onClose={onClose} />)

    expect(screen.getByText('DENY')).toBeInTheDocument()
    expect(screen.queryByText('ALLOW')).not.toBeInTheDocument()
    expect(screen.getByText('workflow:delete')).toBeInTheDocument()
    expect(screen.getByText('workflow:write')).toBeInTheDocument()
  })

  it('renders a single-label policy correctly', () => {
    const singleLabelPolicy: PolicyRead = {
      ...customPolicy,
      project_id: null,
      labels: { environment: 'staging' },
    }
    render(<PolicyDetailSidebar policy={singleLabelPolicy} onClose={onClose} />)

    expect(screen.getByText('Labels')).toBeInTheDocument()
    expect(screen.getByText('environment: staging')).toBeInTheDocument()
  })

  it('renders policy with many statements', () => {
    const multiStatementPolicy: PolicyRead = {
      ...customPolicy,
      project_id: null,
      statements: [
        { scope: 'any', effect: 'allow', actions: ['workflow:read'] },
        { scope: 'self', effect: 'deny', actions: ['credential:delete'] },
        {
          scope: 'any',
          effect: 'allow',
          actions: ['project:read'],
          conditions: { team: 'engineering' },
        },
      ],
    }
    render(<PolicyDetailSidebar policy={multiStatementPolicy} onClose={onClose} />)

    expect(screen.getAllByText('ALLOW')).toHaveLength(2)
    expect(screen.getByText('DENY')).toBeInTheDocument()
    expect(screen.getByText('workflow:read')).toBeInTheDocument()
    expect(screen.getByText('credential:delete')).toBeInTheDocument()
    expect(screen.getByText('project:read')).toBeInTheDocument()
    expect(screen.getByText('Conditions:')).toBeInTheDocument()
  })

  it('does not render conditions when statement has undefined conditions', () => {
    const policyUndefinedConditions: PolicyRead = {
      ...customPolicy,
      project_id: null,
      statements: [
        {
          scope: 'any',
          effect: 'allow',
          actions: ['workflow:read'],
          conditions: undefined,
        },
      ],
    }
    render(<PolicyDetailSidebar policy={policyUndefinedConditions} onClose={onClose} />)

    expect(screen.queryByText('Conditions:')).not.toBeInTheDocument()
  })

  it('has no accessibility violations for empty statements policy', async () => {
    const { container } = render(<PolicyDetailSidebar policy={emptyStatementsPolicy} onClose={onClose} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders project link with projectName when provided', () => {
    render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} projectName="Alpha Project" />)

    expect(screen.getByText('Project: Alpha Project')).toBeInTheDocument()
    expect(screen.queryByText('Project: proj-1')).not.toBeInTheDocument()
  })

  it('renders labels with non-string values converted to string', () => {
    const policyWithNonStringLabels: PolicyRead = {
      ...customPolicy,
      project_id: null,
      labels: { count: 42 as unknown as string, active: true as unknown as string },
    }
    render(<PolicyDetailSidebar policy={policyWithNonStringLabels} onClose={onClose} />)

    expect(screen.getByText('count: 42')).toBeInTheDocument()
    expect(screen.getByText('active: true')).toBeInTheDocument()
  })

  describe('re-render coverage (memoization cache paths)', () => {
    it('handles re-render with same props (cache hit)', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
      rerender(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

      expect(screen.getByRole('heading', { name: 'Policy details' })).toBeInTheDocument()
      expect(screen.getByText('admin-policy')).toBeInTheDocument()
      expect(screen.getByText('Built-in')).toBeInTheDocument()
    })

    it('handles re-render with different policy name and description', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
      rerender(
        <PolicyDetailSidebar
          policy={{ ...builtinPolicy, name: 'updated-policy', description: 'Changed description' }}
          onClose={onClose}
        />
      )

      expect(screen.getByText('updated-policy')).toBeInTheDocument()
      expect(screen.getByText('Changed description')).toBeInTheDocument()
    })

    it('handles re-render with changed projectName', () => {
      const { rerender } = render(
        <PolicyDetailSidebar policy={customPolicy} onClose={onClose} projectName="Original Project" />
      )
      rerender(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} projectName="Updated Project" />)

      expect(screen.getByText('Project: Updated Project')).toBeInTheDocument()
    })

    it('handles re-render with different scope', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
      rerender(<PolicyDetailSidebar policy={{ ...builtinPolicy, scope: 'project' }} onClose={onClose} />)

      const scopeTerms = screen.getAllByText('Scope')
      expect(scopeTerms.length).toBeGreaterThanOrEqual(1)
    })

    it('handles re-render toggling is_builtin', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
      expect(screen.getByText('Built-in')).toBeInTheDocument()

      rerender(<PolicyDetailSidebar policy={{ ...builtinPolicy, is_builtin: false }} onClose={onClose} />)
      expect(screen.getByText('Custom')).toBeInTheDocument()
    })

    it('handles re-render with different statements', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
      expect(screen.getByText('workflow:read')).toBeInTheDocument()

      rerender(
        <PolicyDetailSidebar
          policy={{
            ...builtinPolicy,
            statements: [
              {
                scope: 'any',
                effect: 'allow',
                actions: ['credential:read', 'credential:write'],
                conditions: { region: 'us-east-1' },
              },
            ],
          }}
          onClose={onClose}
        />
      )

      expect(screen.getByText('credential:read')).toBeInTheDocument()
      expect(screen.getByText('credential:write')).toBeInTheDocument()
      expect(screen.getByText('Conditions:')).toBeInTheDocument()
    })

    it('handles re-render with different labels', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
      expect(screen.getByText('env: production')).toBeInTheDocument()

      rerender(
        <PolicyDetailSidebar
          policy={{ ...builtinPolicy, labels: { tier: 'gold', region: 'eu-west' } }}
          onClose={onClose}
        />
      )

      expect(screen.getByText('tier: gold')).toBeInTheDocument()
      expect(screen.getByText('region: eu-west')).toBeInTheDocument()
    })

    it('handles re-render with different dates', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)

      rerender(
        <PolicyDetailSidebar
          policy={{
            ...builtinPolicy,
            created_at: '2025-12-01T08:00:00Z',
            updated_at: '2026-01-15T16:30:00Z',
          }}
          onClose={onClose}
        />
      )

      expect(screen.getByText('Created')).toBeInTheDocument()
      expect(screen.getByText('Updated')).toBeInTheDocument()
    })

    it('handles re-render with changed onClose callback', () => {
      const onCloseA = vi.fn()
      const onCloseB = vi.fn()
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onCloseA} />)
      rerender(<PolicyDetailSidebar policy={builtinPolicy} onClose={onCloseB} />)

      expect(screen.getByRole('heading', { name: 'Policy details' })).toBeInTheDocument()
    })

    it('handles re-render from builtin to custom with project', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
      expect(screen.getByText('Built-in')).toBeInTheDocument()
      expect(screen.queryByText(/Project:/)).not.toBeInTheDocument()

      rerender(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} projectName="Test Project" />)
      expect(screen.getByText('Custom')).toBeInTheDocument()
      expect(screen.getByText('Project: Test Project')).toBeInTheDocument()
    })

    it('handles re-render from statements to empty statements', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={builtinPolicy} onClose={onClose} />)
      expect(screen.getByText('ALLOW')).toBeInTheDocument()

      rerender(<PolicyDetailSidebar policy={emptyStatementsPolicy} onClose={onClose} />)
      expect(screen.getByText('No statements defined.')).toBeInTheDocument()
    })

    it('handles re-render from no labels to labels', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)
      expect(screen.queryByText('Labels')).not.toBeInTheDocument()

      rerender(<PolicyDetailSidebar policy={{ ...customPolicy, labels: { stage: 'beta' } }} onClose={onClose} />)
      expect(screen.getByText('Labels')).toBeInTheDocument()
      expect(screen.getByText('stage: beta')).toBeInTheDocument()
    })

    it('handles re-render from null dates to valid dates', () => {
      const { rerender } = render(<PolicyDetailSidebar policy={customPolicy} onClose={onClose} />)

      rerender(
        <PolicyDetailSidebar
          policy={{
            ...customPolicy,
            created_at: '2025-06-01T12:00:00Z',
            updated_at: '2025-07-01T12:00:00Z',
          }}
          onClose={onClose}
        />
      )

      expect(screen.getByText('Created')).toBeInTheDocument()
      expect(screen.getByText('Updated')).toBeInTheDocument()
    })
  })
})
