import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { PolicyTypeLabel, ProjectLabel, ScopeLabel } from './ScopeLabel'

const projectNameMap = new Map([
  ['proj-1', 'Alpha Project'],
  ['proj-2', 'Beta Project'],
])

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
