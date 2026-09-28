import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

const mockUseCanI = vi.hoisted(() => vi.fn())

vi.mock('../../hooks/useCanI', () => ({
  useCanI: mockUseCanI,
}))

import { useCanI } from '../../hooks/useCanI'

import { NodeExecutionPermissionProvider, NodeExecutionRestriction } from './NodeExecutionRestriction'

describe('NodeExecutionRestriction', () => {
  it('shows an accessible lock when the step type is denied', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    render(
      <NodeExecutionPermissionProvider resourceProject="project-1">
        <NodeExecutionRestriction kind="script" />
      </NodeExecutionPermissionProvider>
    )

    expect(screen.getByRole('img', { name: 'Execution restricted' })).toBeInTheDocument()
    expect(useCanI).toHaveBeenCalledWith('execute', 'workflow_node', {
      resourceProject: 'project-1',
      resourceLabels: { kind: 'script' },
    })
  })

  it('colors the lock with the warning token', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    render(
      <NodeExecutionPermissionProvider resourceProject="project-1">
        <NodeExecutionRestriction kind="script" />
      </NodeExecutionPermissionProvider>
    )

    expect(screen.getByTestId('execution-restriction-icon').getAttribute('style')).toContain(
      'color: var(--pf-t--global--color--status--warning--default)'
    )
  })

  it.each([
    { allowed: true, isChecking: false, isError: false },
    { allowed: false, isChecking: true, isError: false },
    { allowed: false, isChecking: false, isError: true },
  ])('hides the lock unless a resolved check denies execution: %o', (permission) => {
    vi.mocked(useCanI).mockReturnValue(permission)

    render(
      <NodeExecutionPermissionProvider resourceProject="project-1">
        <NodeExecutionRestriction kind="script" />
      </NodeExecutionPermissionProvider>
    )

    expect(screen.queryByRole('img', { name: 'Execution restricted' })).not.toBeInTheDocument()
  })

  it('uses a system-scope check when the builder has no project selected', () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    render(
      <NodeExecutionPermissionProvider>
        <NodeExecutionRestriction kind="script" />
      </NodeExecutionPermissionProvider>
    )

    expect(useCanI).toHaveBeenCalledWith('execute', 'workflow_node', {
      resourceLabels: { kind: 'script' },
    })
  })

  it('does not check permissions outside the workflow builder', () => {
    render(<NodeExecutionRestriction kind="script" />)

    expect(screen.queryByRole('img', { name: 'Execution restricted' })).not.toBeInTheDocument()
    expect(useCanI).not.toHaveBeenCalled()
  })

  it('has no accessibility violations', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })

    const { container } = render(
      <NodeExecutionPermissionProvider resourceProject="project-1">
        <NodeExecutionRestriction kind="script" />
      </NodeExecutionPermissionProvider>
    )

    expect(await axe(container)).toHaveNoViolations()
  })
})
