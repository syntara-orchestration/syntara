import type { ExecutionPlaneAPI } from '@syntara/contracts'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { DialogState } from '../../hooks/useDialogState'

import { ExecutionTargetDialogs } from './ExecutionTargetDialogs'
import { useExecutionTargetUsage } from './useExecutionTargetUsage'

vi.mock('./useExecutionTargetUsage', () => ({
  useExecutionTargetUsage: vi.fn(),
}))

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

function mockUsage(
  overrides: Partial<{
    activeWorkloadCount: number
    isLoadingUsage: boolean
    usageFetchError: boolean
  }> = {}
) {
  vi.mocked(useExecutionTargetUsage).mockReturnValue({
    activeWorkloadCount: 0,
    isLoadingUsage: false,
    usageFetchError: false,
    ...overrides,
  })
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
  beforeEach(() => {
    vi.clearAllMocks()
    mockUsage()
  })

  it('renders the delete confirmation with the target name when open', () => {
    renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(screen.getByText('Delete execution target?')).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/Staging OpenShift/)).toBeInTheDocument()
    expect(within(dialog).getByText(/This cannot be undone/i)).toBeInTheDocument()
    expect(within(dialog).getByRole('checkbox', { name: /permanently deleted/i })).toBeInTheDocument()
  })

  it('shows the active workload count in the delete confirmation', () => {
    mockUsage({ activeWorkloadCount: 7 })
    renderDialogs({ deleteDialog: createDialog(target, true) })

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/7 active workloads/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/deleted after those workloads complete/i)).toBeInTheDocument()
  })

  it('uses singular wording for one active workload in the delete confirmation', () => {
    mockUsage({ activeWorkloadCount: 1 })
    renderDialogs({ deleteDialog: createDialog(target, true) })

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/1 active workload/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/deleted after that workload completes/i)).toBeInTheDocument()
  })

  it('omits the active workload notice from delete when the count is zero', () => {
    mockUsage({ activeWorkloadCount: 0 })
    renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(screen.queryByText(/active workload/i)).not.toBeInTheDocument()
  })

  it('shows a loading state in the delete confirmation while usage is fetching', () => {
    mockUsage({ isLoadingUsage: true })
    renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(screen.getByLabelText('Checking active workloads')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Delete/i })).toBeDisabled()
  })

  it('shows a usage fetch error in the delete confirmation', () => {
    mockUsage({ usageFetchError: true })
    renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(screen.getByText(/Unable to load active workload information/i)).toBeInTheDocument()
  })

  it('fetches usage for the open delete dialog target', () => {
    renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(useExecutionTargetUsage).toHaveBeenCalledWith('et-002')
  })

  it('has no accessibility violations with the delete confirmation dialog open', async () => {
    const { container } = renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(await screen.findByText('Delete execution target?')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with the delete confirmation loading state', async () => {
    mockUsage({ isLoadingUsage: true })
    const { container } = renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(await screen.findByLabelText('Checking active workloads')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with the delete confirmation usage error state', async () => {
    mockUsage({ usageFetchError: true })
    const { container } = renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(await screen.findByText(/Unable to load active workload information/i)).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with the delete confirmation active workload count', async () => {
    mockUsage({ activeWorkloadCount: 7 })
    const { container } = renderDialogs({ deleteDialog: createDialog(target, true) })

    expect(await screen.findByText(/7 active workloads/i)).toBeInTheDocument()
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

  it('renders the disable confirmation with the target name and impact copy when open', () => {
    renderDialogs({ disableDialog: createDialog(target, true) })

    expect(screen.getByText('Disable execution target?')).toBeInTheDocument()
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/Staging OpenShift/)).toBeInTheDocument()
    expect(within(dialog).getByText(/require affinity to this target will fail/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/re-enable it at any time/i)).toBeInTheDocument()
    expect(within(dialog).queryByText(/This will immediately:/i)).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('shows the active workload count in the disable confirmation', () => {
    mockUsage({ activeWorkloadCount: 2 })
    renderDialogs({ disableDialog: createDialog(target, true) })

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/2 active workloads/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/Those workloads will continue to completion/i)).toBeInTheDocument()
  })

  it('uses singular wording for one active workload in the disable confirmation', () => {
    mockUsage({ activeWorkloadCount: 1 })
    renderDialogs({ disableDialog: createDialog(target, true) })

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/1 active workload/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/That workload will continue to completion/i)).toBeInTheDocument()
  })

  it('omits the active workload notice from disable when the count is zero', () => {
    mockUsage({ activeWorkloadCount: 0 })
    renderDialogs({ disableDialog: createDialog(target, true) })

    expect(screen.queryByText(/active workload/i)).not.toBeInTheDocument()
  })

  it('fetches usage for the open disable dialog target', () => {
    renderDialogs({ disableDialog: createDialog(target, true) })

    expect(useExecutionTargetUsage).toHaveBeenCalledWith('et-002')
  })

  it('has no accessibility violations with the disable confirmation dialog open', async () => {
    const { container } = renderDialogs({ disableDialog: createDialog(target, true) })

    expect(await screen.findByText('Disable execution target?')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with the disable confirmation loading state', async () => {
    mockUsage({ isLoadingUsage: true })
    const { container } = renderDialogs({ disableDialog: createDialog(target, true) })

    expect(await screen.findByLabelText('Checking active workloads')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with the disable confirmation usage error state', async () => {
    mockUsage({ usageFetchError: true })
    const { container } = renderDialogs({ disableDialog: createDialog(target, true) })

    expect(await screen.findByText(/Unable to load active workload information/i)).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations with the disable confirmation active workload count', async () => {
    mockUsage({ activeWorkloadCount: 2 })
    const { container } = renderDialogs({ disableDialog: createDialog(target, true) })

    expect(await screen.findByText(/2 active workloads/i)).toBeInTheDocument()
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

  it('does not fetch usage when neither dialog is open', () => {
    renderDialogs()

    expect(useExecutionTargetUsage).toHaveBeenCalledWith(null)
  })
})
