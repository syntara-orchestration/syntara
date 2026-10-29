import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { PolicyTypeLabel, ProjectLabel, ScopeLabel, StatementsCell } from './ScopeLabel'
import type { PolicyStatement } from './types'

const stepStatement: PolicyStatement = {
  effect: 'allow',
  actions: ['step_type:write'],
  scope: 'project',
  conditions: { resource_labels: { kind: 'script' } },
}

const projectNameMap = new Map([
  ['proj-1', 'Alpha Project'],
  ['proj-2', 'Beta Project'],
])

describe('StatementsCell step types', () => {
  it('shows the step type alongside its action and scope', () => {
    render(<StatementsCell statements={[stepStatement]} />)
    expect(screen.getByText('Step type: script')).toBeInTheDocument()
    expect(screen.getByText('step_type:write')).toBeInTheDocument()
    expect(screen.getByText('Scope: project')).toBeInTheDocument()
  })

  it('distinguishes excluded step types', () => {
    render(
      <StatementsCell statements={[{ ...stepStatement, conditions: { resource_labels_not: { kind: 'script' } } }]} />
    )
    expect(screen.getByText('Step type except: script')).toBeInTheDocument()
  })

  it.each([{}, { resource_labels: null }, { resource_labels: { kind: [] } }, { unrelated: { kind: 'script' } }])(
    'omits a step label for absent or malformed kind conditions %j',
    (conditions) => {
      render(<StatementsCell statements={[{ ...stepStatement, conditions }]} />)
      expect(screen.queryByText('Step type: script')).not.toBeInTheDocument()
      expect(screen.getByText('step_type:write')).toBeInTheDocument()
    }
  )

  it('does not interpret kind labels on other resource types', () => {
    render(<StatementsCell statements={[{ ...stepStatement, actions: ['workflow:read'] }]} />)
    expect(screen.queryByText('Step type: script')).not.toBeInTheDocument()
    expect(screen.getByText('workflow:read')).toBeInTheDocument()
  })

  it('renders multiple kinds with the same action and scope accessibly', async () => {
    const { container } = render(
      <StatementsCell
        statements={[stepStatement, { ...stepStatement, conditions: { resource_labels: { kind: 'manual_trigger' } } }]}
      />
    )
    expect(screen.getByText('Step type: script')).toBeInTheDocument()
    expect(screen.getByText('Step type: manual_trigger')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('PolicyTypeLabel', () => {
  it('has no accessibility violations for built-in policy', async () => {
    const { container } = render(<PolicyTypeLabel isBuiltin />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations for custom policy', async () => {
    const { container } = render(<PolicyTypeLabel isBuiltin={false} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders "Built-in" label with lock icon when isBuiltin is true', () => {
    render(<PolicyTypeLabel isBuiltin />)
    expect(screen.getByText('Built-in')).toBeInTheDocument()
  })

  it('renders "Custom" label when isBuiltin is false', () => {
    render(<PolicyTypeLabel isBuiltin={false} />)
    expect(screen.getByText('Custom')).toBeInTheDocument()
  })

  it('renders "Custom" label when isBuiltin is undefined', () => {
    render(<PolicyTypeLabel />)
    expect(screen.getByText('Custom')).toBeInTheDocument()
  })
})

describe('ScopeLabel', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<ScopeLabel scope="system" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders "System" for system scope', () => {
    render(<ScopeLabel scope="system" />)
    expect(screen.getByText('System')).toBeInTheDocument()
  })

  it('renders "Any" for any scope', () => {
    render(<ScopeLabel scope="any" />)
    expect(screen.getByText('Any')).toBeInTheDocument()
  })

  it('renders "Self" for self scope', () => {
    render(<ScopeLabel scope="self" />)
    expect(screen.getByText('Self')).toBeInTheDocument()
  })

  it('renders "Project" for project scope', () => {
    render(<ScopeLabel scope="project" />)
    expect(screen.getByText('Project')).toBeInTheDocument()
  })

  it('defaults to "System" when scope is null', () => {
    render(<ScopeLabel />)
    expect(screen.getByText('System')).toBeInTheDocument()
  })
})

describe('ProjectLabel', () => {
  it('has no accessibility violations for project scope', async () => {
    const { container } = render(<ProjectLabel projectId="proj-1" projectNameMap={projectNameMap} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders "-" when no projectId is provided', () => {
    const { container } = render(<ProjectLabel projectNameMap={projectNameMap} />)
    expect(container.textContent).toBe('-')
  })

  it('renders project name when projectId is provided', () => {
    render(<ProjectLabel projectId="proj-1" projectNameMap={projectNameMap} />)
    expect(screen.getByText('Alpha Project')).toBeInTheDocument()
  })

  it('falls back to projectId when name is not in the map', () => {
    render(<ProjectLabel projectId="unknown-id" projectNameMap={projectNameMap} />)
    expect(screen.getByText('unknown-id')).toBeInTheDocument()
  })

  it('is keyboard accessible', async () => {
    const user = userEvent.setup()
    render(<ProjectLabel projectId="proj-1" projectNameMap={projectNameMap} />)

    const link = screen.getByRole('link', { name: /alpha project/i })
    expect(link).toBeInTheDocument()

    await user.tab()
    expect(link).toHaveFocus()
  })

  it('links to the project detail page', () => {
    render(<ProjectLabel projectId="proj-1" projectNameMap={projectNameMap} />)

    expect(screen.getByRole('link', { name: /alpha project/i })).toHaveAttribute(
      'href',
      '/system-administration/access-management/projects/proj-1'
    )
  })
})
