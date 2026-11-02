import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { DialogState } from '../../hooks/useDialogState'

import { ExecutionTargetDialogs } from './ExecutionTargetDialogs'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetFacadeRead']

function createDeleteDialog(item: ExecutionTarget | null = null, isOpen = false): DialogState<ExecutionTarget> {
  return {
    isOpen,
    item,
    open: vi.fn(),
    close: vi.fn(),
  }
}

const target: ExecutionTarget = {
  id: 'et-002',
  cluster_id: 'cl-002',
  name: 'Staging OpenShift',
  backend_type: 'kubernetes',
  endpoint: 'https://api.staging.example.com',
  placement: {
    type: 'kubernetes',
    namespace: 'syntara-staging',
    node_selectors: [],
    tolerations: [],
  },
  status: 'active',
  enabled: true,
  is_default: false,
  status_message: null,
  labels: {},
  created_at: '2026-01-02T00:00:00Z',
  last_ran_at: null,
}

describe('ExecutionTargetDialogs', () => {
  it('renders the delete confirmation with the target name when open', () => {
    const deleteDialog = createDeleteDialog(target, true)
    render(<ExecutionTargetDialogs deleteDialog={deleteDialog} onDelete={vi.fn()} />)

    expect(screen.getByText('Delete execution target?')).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/Staging OpenShift/)).toBeInTheDocument()
    expect(within(dialog).getByRole('checkbox', { name: /permanently deleted/i })).toBeInTheDocument()
  })

  it('has no accessibility violations with the delete confirmation dialog open', async () => {
    const deleteDialog = createDeleteDialog(target, true)
    const { container } = render(<ExecutionTargetDialogs deleteDialog={deleteDialog} onDelete={vi.fn()} />)

    expect(await screen.findByText('Delete execution target?')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('calls onDelete after acknowledgement and confirm', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    const deleteDialog = createDeleteDialog(target, true)
    render(<ExecutionTargetDialogs deleteDialog={deleteDialog} onDelete={onDelete} />)

    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('checkbox', { name: /permanently deleted/i }))
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it('calls deleteDialog.close when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const deleteDialog = createDeleteDialog(target, true)
    render(<ExecutionTargetDialogs deleteDialog={deleteDialog} onDelete={vi.fn()} />)

    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    expect(deleteDialog.close).toHaveBeenCalledTimes(1)
  })
})
