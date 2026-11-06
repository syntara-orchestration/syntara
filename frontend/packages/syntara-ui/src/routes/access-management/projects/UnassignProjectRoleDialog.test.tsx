import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { RoleAssignmentRead } from '../../access/types'

import { UnassignProjectRoleDialog } from './UnassignProjectRoleDialog'

const mockAssignment: RoleAssignmentRead = {
  id: 'a1',
  principal_id: 'u1',
  group_id: null,
  principal_name: 'alice',
  project_id: 'p1',
  role_name: 'project-admin',
  created_at: '2024-01-01T00:00:00Z',
}

describe('UnassignProjectRoleDialog', () => {
  it('has no accessibility violations when open', async () => {
    const { container } = render(
      <UnassignProjectRoleDialog assignment={mockAssignment} isOpen={true} onClose={vi.fn()} onConfirm={vi.fn()} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders the role name and username in the confirmation message', () => {
    render(
      <UnassignProjectRoleDialog assignment={mockAssignment} isOpen={true} onClose={vi.fn()} onConfirm={vi.fn()} />
    )
    expect(screen.getByText(/project-admin/)).toBeInTheDocument()
    expect(screen.getByText(/alice/)).toBeInTheDocument()
  })

  it('calls onConfirm when the Unassign button is clicked', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()

    render(
      <UnassignProjectRoleDialog assignment={mockAssignment} isOpen={true} onClose={vi.fn()} onConfirm={onConfirm} />
    )

    await user.click(screen.getByRole('button', { name: 'Unassign role' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('calls onClose when the Cancel button is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(
      <UnassignProjectRoleDialog assignment={mockAssignment} isOpen={true} onClose={onClose} onConfirm={vi.fn()} />
    )

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('renders dialog when assignment is null (handles optional chaining)', () => {
    render(<UnassignProjectRoleDialog assignment={null} isOpen={true} onClose={vi.fn()} onConfirm={vi.fn()} />)

    expect(screen.getByText('Unassign role?')).toBeInTheDocument()
    expect(screen.getByText(/Related permissions will be revoked/)).toBeInTheDocument()
  })

  it('does not render dialog content when isOpen is false', () => {
    render(
      <UnassignProjectRoleDialog assignment={mockAssignment} isOpen={false} onClose={vi.fn()} onConfirm={vi.fn()} />
    )

    expect(screen.queryByText('Unassign role?')).not.toBeInTheDocument()
  })

  it('renders warning icon in the title', () => {
    render(
      <UnassignProjectRoleDialog assignment={mockAssignment} isOpen={true} onClose={vi.fn()} onConfirm={vi.fn()} />
    )

    expect(screen.getByText('Unassign role?')).toBeInTheDocument()
  })

  it('has no accessibility violations when assignment is null', async () => {
    const { container } = render(
      <UnassignProjectRoleDialog assignment={null} isOpen={true} onClose={vi.fn()} onConfirm={vi.fn()} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
