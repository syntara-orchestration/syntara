import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { useCanI } from '../../hooks/useCanI'
import { useExecutionWebSocket } from '../workflows/hooks/useExecutionWebSocket'

import { FlatExecutionsTableBody, GroupedExecutionsTableBody } from './ExecutionsTableBody'
import { useCancelExecution } from './useCancelExecution'

const mockHandleCancel = vi.fn()

vi.mock('../../hooks/routing/useLocation', () => ({
  useLocation: vi.fn(() => '/executions'),
}))
vi.mock('../../hooks/routing/useNavigate', () => ({
  useNavigate: vi.fn(() => vi.fn()),
}))
vi.mock('../../components/WorkflowName', () => ({
  WorkflowName: ({ workflowId }: { workflowId: string }) => <span>{workflowId}</span>,
}))
vi.mock('../../components/SynLink', () => ({
  SynLink: ({ to, children }: { to: string; children: React.ReactNode }) => <a href={to}>{children}</a>,
}))

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('./useCancelExecution', () => ({
  useCancelExecution: vi.fn(() => ({ handleCancel: mockHandleCancel, isPending: false })),
}))

vi.mock('../workflows/hooks/useExecutionWebSocket', () => ({
  useExecutionWebSocket: vi.fn(() => ({
    isConnected: false,
    isStale: false,
    isComplete: false,
    error: undefined,
    connect: vi.fn(),
    disconnect: vi.fn(),
  })),
}))

vi.mock('./useRetryExecution', () => ({
  useRetryExecution: vi.fn(() => ({ handleRetry: vi.fn(), isPending: false })),
}))

vi.mock('./hooks/useIsCurrentVersion', () => ({
  useIsCurrentVersion: vi.fn(() => ({ isCurrentVersion: true, versionLabel: 'v1', isLoading: false })),
}))

vi.mock('../../client', () => ({
  executionsClient: {
    useMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
    useQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function renderTable(executions: Parameters<typeof FlatExecutionsTableBody>[0]['executions']) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <table>
        <FlatExecutionsTableBody executions={executions} />
      </table>
    </QueryClientProvider>
  )
}

describe('ExecutionsTableBody - Run ID column', () => {
  it('renders Run ID as the first data cell with the execution id', () => {
    const executionId = '123e4567-e89b-12d3-a456-426614174000'
    renderTable([
      {
        id: executionId,
        workflow_id: 'wf-1',
        status: 'completed',
        completed_at: '2025-01-01T10:00:00Z',
        project_id: 'project-1',
      },
    ])

    expect(screen.getByText(executionId)).toBeInTheDocument()

    const cells = screen.getAllByRole('cell')
    expect(cells[0]).toHaveTextContent(executionId)
    expect(cells[1]).toHaveTextContent('wf-1')
  })

  it('links Run ID to the execution detail route', () => {
    const executionId = '223e4567-e89b-12d3-a456-426614174001'
    renderTable([
      {
        id: executionId,
        workflow_id: 'wf-2',
        status: 'running',
        completed_at: null,
        project_id: 'project-1',
      },
    ])

    expect(screen.getByRole('link', { name: executionId })).toHaveAttribute('href', `/executions/${executionId}`)
  })

  it('keeps Run ID first when workflow name is unavailable', () => {
    const executionId = '323e4567-e89b-12d3-a456-426614174002'
    renderTable([
      {
        id: executionId,
        status: 'pending',
        completed_at: null,
        project_id: 'project-1',
      },
    ])

    const cells = screen.getAllByRole('cell')
    expect(cells[0]).toHaveTextContent(executionId)
    expect(cells[1]).toHaveTextContent('—')
    expect(screen.getByRole('link', { name: executionId })).toHaveAttribute('href', `/executions/${executionId}`)
  })

  it('renders Run ID first in grouped project rows', () => {
    const executionId = '423e4567-e89b-12d3-a456-426614174003'
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <table>
          <GroupedExecutionsTableBody
            groupedExecutions={
              new Map([
                [
                  'project-1',
                  {
                    project: { id: 'project-1', name: 'Project One' },
                    executions: [
                      {
                        id: executionId,
                        workflow_id: 'wf-3',
                        status: 'completed',
                        completed_at: '2025-01-01T10:00:00Z',
                        project_id: 'project-1',
                      },
                    ],
                  },
                ],
              ])
            }
            collapsedProjects={new Set()}
            onToggleProject={vi.fn()}
          />
        </table>
      </QueryClientProvider>
    )

    const runIdLink = screen.getByRole('link', { name: executionId })
    expect(runIdLink).toHaveAttribute('href', `/executions/${executionId}`)

    const rows = screen.getAllByRole('row')
    const executionRow = rows.find((row) => within(row).queryByRole('link', { name: executionId }) !== null)
    expect(executionRow).toBeDefined()
    expect(within(executionRow!).getAllByRole('cell')[0]).toHaveTextContent(executionId)
  })
})

describe('ExecutionsTableBody - Pending Approval Badge', () => {
  it('shows "Pending approval" badge when approval_pending is true', () => {
    renderTable([
      {
        id: 'exec-1',
        workflow_id: 'wf-1',
        status: 'paused',
        approval_pending: true,
        completed_at: null,
        project_id: 'project-1',
      },
    ])

    expect(screen.getByText('Pending approval')).toBeInTheDocument()
  })

  it('does not show "Pending approval" badge when approval_pending is false', () => {
    renderTable([
      {
        id: 'exec-2',
        workflow_id: 'wf-1',
        status: 'paused',
        approval_pending: false,
        completed_at: null,
        project_id: 'project-1',
      },
    ])

    expect(screen.queryByText('Pending approval')).not.toBeInTheDocument()
  })

  it('does not show "Pending approval" badge when approval_pending is undefined', () => {
    renderTable([
      {
        id: 'exec-3',
        workflow_id: 'wf-1',
        status: 'running',
        completed_at: null,
        project_id: 'project-1',
      },
    ])

    expect(screen.queryByText('Pending approval')).not.toBeInTheDocument()
  })

  it('shows badge alongside Running status for parallel branch case', () => {
    renderTable([
      {
        id: 'exec-4',
        workflow_id: 'wf-1',
        status: 'running',
        approval_pending: true,
        completed_at: null,
        project_id: 'project-1',
      },
    ])

    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText('Pending approval')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = renderTable([
      {
        id: 'exec-1',
        workflow_id: 'wf-1',
        status: 'running',
        approval_pending: true,
        completed_at: null,
        project_id: 'project-1',
      },
    ])

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('ExecutionsTableBody - Cancel Run Action', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useCanI).mockReturnValue({ allowed: true, isChecking: false, isError: false })
    vi.mocked(useCancelExecution).mockReturnValue({ handleCancel: mockHandleCancel, isPending: false })
  })

  it('passes resourceProject to useCanI for execution row actions', () => {
    renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'proj-99' }])

    expect(useCanI).toHaveBeenCalledWith('run', 'execution', { resourceProject: 'proj-99' })
  })

  it.each(['running', 'pending', 'paused'] as const)(
    'shows kebab with "Cancel run" for %s executions',
    async (status) => {
      const user = userEvent.setup()
      renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status, completed_at: null, project_id: 'project-1' }])

      const kebab = screen.getByRole('button', { name: /actions for execution/i })
      await user.click(kebab)

      expect(screen.getByText('Cancel run')).toBeInTheDocument()
    }
  )

  it.each(['completed', 'completed_with_errors', 'failed', 'cancelled'] as const)(
    'does not show "Cancel run" for %s executions',
    async (status) => {
      const user = userEvent.setup()
      renderTable([
        { id: 'exec-1', workflow_id: 'wf-1', status, completed_at: '2026-01-01T00:00:00Z', project_id: 'project-1' },
      ])

      const kebab = screen.getByRole('button', { name: /actions for execution/i })
      await user.click(kebab)

      expect(screen.queryByText('Cancel run')).not.toBeInTheDocument()
    }
  )

  it('calls handleCancel when "Cancel run" is clicked', async () => {
    const user = userEvent.setup()
    renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' }])

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)
    await user.click(screen.getByText('Cancel run'))

    expect(mockHandleCancel).toHaveBeenCalledTimes(1)
  })

  it('passes the execution id to useCancelExecution', () => {
    renderTable([
      { id: 'exec-abc', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' },
    ])

    expect(useCancelExecution).toHaveBeenCalledWith('exec-abc')
  })

  it('disables "Cancel run" when user lacks execution:run permission', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    const user = userEvent.setup()
    renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' }])

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)

    expect(screen.getByRole('menuitem', { name: /cancel run/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('disables "Cancel run" while cancel mutation is pending', async () => {
    vi.mocked(useCancelExecution).mockReturnValue({ handleCancel: mockHandleCancel, isPending: true })
    const user = userEvent.setup()
    renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' }])

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)

    expect(screen.getByRole('menuitem', { name: /cancel run/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('shows "Cancellation in progress" tooltip while cancel mutation is pending', async () => {
    vi.mocked(useCancelExecution).mockReturnValue({ handleCancel: mockHandleCancel, isPending: true })
    const user = userEvent.setup()
    renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' }])

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)
    await user.hover(screen.getByRole('menuitem', { name: /cancel run/i }))

    expect(await screen.findByText(/cancellation in progress/i)).toBeInTheDocument()
  })

  it('stays disabled after cancel is clicked to prevent duplicate requests', async () => {
    const user = userEvent.setup()
    renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' }])

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)
    await user.click(screen.getByText('Cancel run'))

    await user.click(kebab)
    expect(screen.getByRole('menuitem', { name: /cancel run/i })).toHaveAttribute('aria-disabled', 'true')
  })

  it('does not show a confirmation dialog when "Cancel run" is clicked', async () => {
    const user = userEvent.setup()
    renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' }])

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)
    await user.click(screen.getByText('Cancel run'))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows "Retry run" for retryable statuses (not cancel)', async () => {
    const user = userEvent.setup()
    renderTable([
      {
        id: 'exec-1',
        workflow_id: 'wf-1',
        status: 'failed',
        completed_at: '2026-01-01T00:00:00Z',
        project_id: 'project-1',
      },
    ])

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)

    expect(screen.getByText('Retry run')).toBeInTheDocument()
    expect(screen.queryByText('Cancel run')).not.toBeInTheDocument()
  })

  it('enables WebSocket streaming after cancel to detect status change', async () => {
    const user = userEvent.setup()
    renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' }])

    expect(useExecutionWebSocket).toHaveBeenLastCalledWith('exec-1', expect.objectContaining({ enabled: false }))

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)
    await user.click(screen.getByText('Cancel run'))

    expect(useExecutionWebSocket).toHaveBeenLastCalledWith('exec-1', expect.objectContaining({ enabled: true }))
  })

  it('invokes query invalidation when WebSocket fires onExecutionComplete after cancel', async () => {
    let capturedOnComplete: (() => void) | undefined
    vi.mocked(useExecutionWebSocket).mockImplementation((_id, opts) => {
      capturedOnComplete = opts?.onExecutionComplete
      return {
        isConnected: false,
        isStale: false,
        isComplete: false,
        error: undefined,
        connect: vi.fn(),
        disconnect: vi.fn(),
      }
    })

    const user = userEvent.setup()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue()

    render(
      <QueryClientProvider client={queryClient}>
        <table>
          <FlatExecutionsTableBody
            executions={[
              { id: 'exec-ws', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' },
            ]}
          />
        </table>
      </QueryClientProvider>
    )

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)
    await user.click(screen.getByText('Cancel run'))

    expect(capturedOnComplete).toBeDefined()
    capturedOnComplete!()

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['get', '/executions/{execution_id}'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['get', '/executions'] })
  })

  it('shows permission tooltip when user lacks execution:run and hovers cancel', async () => {
    vi.mocked(useCanI).mockReturnValue({ allowed: false, isChecking: false, isError: false })
    const user = userEvent.setup()
    renderTable([{ id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' }])

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)
    await user.hover(screen.getByRole('menuitem', { name: /cancel run/i }))

    expect(await screen.findByText(/execution:run/i)).toBeInTheDocument()
  })

  it('opens retry dialog when "Retry run" is clicked and closes on cancel', async () => {
    const user = userEvent.setup()
    renderTable([
      {
        id: 'exec-1',
        workflow_id: 'wf-1',
        status: 'failed',
        completed_at: '2026-01-01T00:00:00Z',
        project_id: 'project-1',
      },
    ])

    const kebab = screen.getByRole('button', { name: /actions for execution/i })
    await user.click(kebab)
    await user.click(screen.getByText('Retry run'))

    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('has no accessibility violations for a running execution with kebab', async () => {
    const { container } = renderTable([
      { id: 'exec-1', workflow_id: 'wf-1', status: 'running', completed_at: null, project_id: 'project-1' },
    ])

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
