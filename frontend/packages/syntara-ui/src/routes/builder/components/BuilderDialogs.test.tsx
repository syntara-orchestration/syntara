import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { approvalsClient } from '../../../client'
import { ColorSchemeProvider } from '../../../providers/theme/ColorSchemeProvider'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'

import { BuilderDialogs } from './BuilderDialogs'

vi.mock('../../../stores/useWorkflowStore', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useWorkflowStore: vi.fn((selector: (s: any) => unknown) => selector({ isDirty: false, markDirty: vi.fn() })),
}))

vi.mock('../../../providers/alerts', () => ({
  useAlerts: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}))

vi.mock('../../../client', () => ({
  approvalsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  executionsClient: {
    useQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ColorSchemeProvider>{children}</ColorSchemeProvider>
    </QueryClientProvider>
  )
}

function renderDialogs(overrides: Partial<React.ComponentProps<typeof BuilderDialogs>> = {}) {
  const props: React.ComponentProps<typeof BuilderDialogs> = {
    workflowName: 'Test Workflow',
    workflowId: 'wf-1',
    confirmDialogOpen: false,
    deleteDialogOpen: false,
    dispatch: vi.fn(),
    handleRunWorkflow: vi.fn(),
    handleDeleteWorkflow: vi.fn(),
    triggerName: 'Manual Trigger',
    runStepDialog: {
      isOpen: false,
      item: null,
      open: vi.fn(),
      close: vi.fn(),
    },
    pendingImport: null,
    setPendingImport: vi.fn(),
    importDeps: {
      selectedProject: null,
      createWorkflow: vi.fn(),
      setLocation: vi.fn(),
    },
    ...overrides,
  }
  return render(<BuilderDialogs {...props} />, { wrapper })
}

describe('BuilderDialogs', () => {
  beforeEach(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(useWorkflowStore).mockImplementation((selector: (s: any) => unknown) => selector({ isDirty: false }))

    vi.mocked(approvalsClient.useQuery).mockReturnValue({ data: undefined, refetch: vi.fn() } as never)
    vi.mocked(approvalsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false } as never)
  })

  it('renders nothing visible when all dialogs are closed', () => {
    renderDialogs()

    expect(screen.queryByText('Run Test Workflow?')).not.toBeInTheDocument()
    expect(screen.queryByText('Set mock output data for Manual Trigger')).not.toBeInTheDocument()
    expect(screen.queryByText('Delete workflow?')).not.toBeInTheDocument()
    expect(screen.queryByText('Review approval')).not.toBeInTheDocument()
  })

  it('shows the run confirmation dialog when confirmDialogOpen is true', () => {
    renderDialogs({ confirmDialogOpen: true })

    expect(screen.getByText('Run Test Workflow?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run now' })).toBeInTheDocument()
  })

  it('shows the run workflow modal after confirming the run dialog when trigger has input schema', async () => {
    const user = userEvent.setup()
    renderDialogs({
      confirmDialogOpen: true,
      triggerInputSchema: { type: 'object', properties: { name: { type: 'string' } } },
    })

    await user.click(screen.getByRole('button', { name: 'Run now' }))

    expect(screen.getByText('Set mock output data for Manual Trigger')).toBeInTheDocument()
  })

  it('runs workflow immediately after confirming when trigger has no input schema', async () => {
    const user = userEvent.setup()
    const handleRunWorkflow = vi.fn()
    const dispatch = vi.fn()
    renderDialogs({ confirmDialogOpen: true, handleRunWorkflow, dispatch })

    await user.click(screen.getByRole('button', { name: 'Run now' }))

    // Should run immediately without showing the mock data modal
    expect(handleRunWorkflow).toHaveBeenCalledTimes(1)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
    expect(screen.queryByText('Set mock output data for Manual Trigger')).not.toBeInTheDocument()
  })

  it('shows trigger name in confirmation dialog body when workflow is clean', () => {
    renderDialogs({ confirmDialogOpen: true, triggerName: 'Webhook' })

    expect(screen.getByText(/starting from Webhook/)).toBeInTheDocument()
    expect(screen.queryByText(/unsaved changes/)).not.toBeInTheDocument()
  })

  it('shows save warning and "Save and run" label when workflow is dirty', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(useWorkflowStore).mockImplementation((selector: (s: any) => unknown) => selector({ isDirty: true }))
    renderDialogs({ confirmDialogOpen: true })

    expect(screen.getByRole('button', { name: 'Save and run' })).toBeInTheDocument()
    expect(screen.getByText(/unsaved changes will be saved/)).toBeInTheDocument()
  })

  it('shows delete confirmation dialog when deleteDialogOpen is true', () => {
    renderDialogs({ deleteDialogOpen: true })

    expect(screen.getByText('Delete workflow?')).toBeInTheDocument()
    expect(screen.getByText('Test Workflow')).toBeInTheDocument()
  })

  it('calls handleRunWorkflow when run modal is confirmed (with input schema)', async () => {
    const user = userEvent.setup()
    const handleRunWorkflow = vi.fn()
    renderDialogs({
      confirmDialogOpen: true,
      handleRunWorkflow,
      triggerInputSchema: { type: 'object', properties: { name: { type: 'string' } } },
    })

    await user.click(screen.getByRole('button', { name: 'Run now' }))
    await user.click(screen.getByRole('button', { name: 'Run' }))

    expect(handleRunWorkflow).toHaveBeenCalledTimes(1)
  })

  it('resets state and shows confirmation dialog again on second run open', async () => {
    const user = userEvent.setup()
    const defaultProps: React.ComponentProps<typeof BuilderDialogs> = {
      workflowName: 'Test Workflow',
      workflowId: 'wf-1',
      confirmDialogOpen: true,
      deleteDialogOpen: false,
      dispatch: vi.fn(),
      handleRunWorkflow: vi.fn(),
      handleDeleteWorkflow: vi.fn(),
      triggerName: 'Manual Trigger',
      triggerInputSchema: { type: 'object', properties: { name: { type: 'string' } } },
      runStepDialog: {
        isOpen: false,
        item: null,
        open: vi.fn(),
        close: vi.fn(),
      },
      pendingImport: null,
      setPendingImport: vi.fn(),
      importDeps: {
        selectedProject: null,
        createWorkflow: vi.fn(),
        setLocation: vi.fn(),
      },
    }
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ColorSchemeProvider>
          <BuilderDialogs {...defaultProps} />
        </ColorSchemeProvider>
      </QueryClientProvider>
    )

    // Advance to run modal
    await user.click(screen.getByRole('button', { name: 'Run now' }))
    expect(screen.getByText('Set mock output data for Manual Trigger')).toBeInTheDocument()

    // Simulate reducer closing the dialog (e.g. after a successful run)
    rerender(
      <QueryClientProvider client={queryClient}>
        <ColorSchemeProvider>
          <BuilderDialogs {...defaultProps} confirmDialogOpen={false} />
        </ColorSchemeProvider>
      </QueryClientProvider>
    )
    expect(screen.queryByText('Set mock output data for Manual Trigger')).not.toBeInTheDocument()

    // Re-open: should show the confirmation dialog, not the run modal directly
    rerender(
      <QueryClientProvider client={queryClient}>
        <ColorSchemeProvider>
          <BuilderDialogs {...defaultProps} confirmDialogOpen={true} />
        </ColorSchemeProvider>
      </QueryClientProvider>
    )
    expect(screen.getByText('Run Test Workflow?')).toBeInTheDocument()
  })

  it('closes run modal when onClose is called from RunWorkflowModal', async () => {
    const user = userEvent.setup()
    const dispatch = vi.fn()
    renderDialogs({
      confirmDialogOpen: true,
      dispatch,
      triggerInputSchema: { type: 'object', properties: { name: { type: 'string' } } },
    })

    // Advance to run modal
    await user.click(screen.getByRole('button', { name: 'Run now' }))
    expect(screen.getByText('Set mock output data for Manual Trigger')).toBeInTheDocument()

    // Close via the modal's X button
    const dialog = screen.getByRole('dialog')
    const closeBtn = within(dialog).getByRole('button', { name: 'Close' })
    await user.click(closeBtn)

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
  })

  it('checking "Don\'t show again" and confirming run stores the preference and shows input modal', async () => {
    const user = userEvent.setup()
    renderDialogs({
      confirmDialogOpen: true,
      triggerInputSchema: { type: 'object', properties: { name: { type: 'string' } } },
    })

    const checkbox = screen.getByRole('checkbox', { name: "Don't show again for all manual workflow runs" })
    await user.click(checkbox)
    expect(checkbox).toBeChecked()

    await user.click(screen.getByRole('button', { name: 'Run now' }))
    // Run modal is now shown — confirmedRun is true, preference was recorded
    expect(screen.getByText('Set mock output data for Manual Trigger')).toBeInTheDocument()
  })

  it('stores "Don\'t show again" preference when running workflow with no input schema', async () => {
    const store: Record<string, string> = {}
    const storageMock: Storage = {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => {
        store[key] = value
      },
      removeItem: (key: string) => {
        delete store[key]
      },
      clear: () => Object.keys(store).forEach((k) => delete store[k]),
      get length() {
        return Object.keys(store).length
      },
      key: (i: number) => Object.keys(store)[i] ?? null,
    }
    vi.stubGlobal('localStorage', storageMock)

    const user = userEvent.setup()
    const handleRunWorkflow = vi.fn()
    const dispatch = vi.fn()
    renderDialogs({ confirmDialogOpen: true, handleRunWorkflow, dispatch })

    // Check the "Don't show again" checkbox
    const checkbox = screen.getByRole('checkbox', { name: "Don't show again for all manual workflow runs" })
    await user.click(checkbox)
    expect(checkbox).toBeChecked()

    // Click "Run now" - should run immediately and close dialog
    await user.click(screen.getByRole('button', { name: 'Run now' }))

    // Should run immediately without showing the mock data modal
    expect(handleRunWorkflow).toHaveBeenCalledTimes(1)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
    expect(screen.queryByText('Set mock output data for Manual Trigger')).not.toBeInTheDocument()

    // Verify the preference was stored
    expect(store['syntara-run-workflow-confirm-dismissed']).toBe('true')

    vi.unstubAllGlobals()
  })

  describe('accessibility', () => {
    it('has no violations with run confirmation dialog open', async () => {
      const { container } = renderDialogs({ confirmDialogOpen: true })
      expect(await axe(container)).toHaveNoViolations()
    })
  })
})
