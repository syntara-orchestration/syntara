import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { DialogState } from '../../hooks/useDialogState'

import { ExecutionTargetDialogs } from './ExecutionTargetDialogs'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

function createDialog(item: ExecutionTarget | null = null, isOpen = false): DialogState<ExecutionTarget> {
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

function renderDialogs(
  overrides: Partial<{
    deleteDialog: DialogState<ExecutionTarget>
    onDelete: () => void
    disableDialog: DialogState<ExecutionTarget>
    onDisable: () => void
  }> = {}
) {
  const props = {
    deleteDialog: createDialog(),
    onDelete: vi.fn(),
    disableDialog: createDialog(),
    onDisable: vi.fn(),
    ...overrides,
  }
  return { ...render(<ExecutionTargetDialogs {...props} />), props }
}

describe('ExecutionTargetDialogs', () => {
  it('renders the delete confirmation with the target name when open', () => {
    renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(screen.getByText('Delete execution target?')).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/Staging OpenShift/)).toBeInTheDocument()
    expect(within(dialog).getByRole('checkbox', { name: /permanently deleted/i })).toBeInTheDocument()
  })

  it('has no accessibility violations with the delete confirmation dialog open', async () => {
    const { container } = renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(await screen.findByText('Delete execution target?')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('calls onDelete after acknowledgement and confirm', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    renderDialogs({ deleteDialog: createDialog(target, true), onDelete })

    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('checkbox', { name: /permanently deleted/i }))
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it('calls deleteDialog.close when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const deleteDialog = createDialog(target, true)
    renderDialogs({ deleteDialog })

    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    expect(deleteDialog.close).toHaveBeenCalledTimes(1)
  })

  it('renders the disable confirmation with the target name and impact bullets when open', () => {
    renderDialogs({ disableDialog: createDialog(target, true) })

    expect(screen.getByText('Disable execution target?')).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/Staging OpenShift/)).toBeInTheDocument()
    expect(within(dialog).getByText(/This will immediately:/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/continue to completion/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/require affinity to this target will fail/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/shift to other available capacity/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/re-enable this execution target at any time/i)).toBeInTheDocument()
    expect(within(dialog).queryByText(/Resources that will be affected/i)).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('has no accessibility violations with the disable confirmation dialog open', async () => {
    const { container } = renderDialogs({ disableDialog: createDialog(target, true) })

    expect(await screen.findByText('Disable execution target?')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('calls onDisable when Disable is confirmed', async () => {
    const user = userEvent.setup()
    const onDisable = vi.fn()
    renderDialogs({ disableDialog: createDialog(target, true), onDisable })

    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Disable' }))
    expect(onDisable).toHaveBeenCalledTimes(1)
  })

  it('calls disableDialog.close when Cancel is clicked on the disable dialog', async () => {
    const user = userEvent.setup()
    const disableDialog = createDialog(target, true)
    renderDialogs({ disableDialog })

    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    expect(disableDialog.close).toHaveBeenCalledTimes(1)
  })
})
