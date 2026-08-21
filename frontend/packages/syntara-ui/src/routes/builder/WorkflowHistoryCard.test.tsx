import { SimpleList } from '@patternfly/react-core'
import type { ExecutionsAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCanI } from '../../hooks/useCanI'

import { WorkflowHistoryCard, ExecutionHistoryRow } from './WorkflowHistoryCard'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']

vi.mock('../../client', () => ({
  workflowClient: {
    useQuery: vi.fn(() => ({ data: null, isLoading: false, error: null })),
  },
  executionsClient: {
    useMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}))

const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function TestWrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={testQueryClient}>{children}</QueryClientProvider>
}

vi.mock('../../hooks/routing/Link', () => ({
  Link: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock('./ExecutionStatus', () => ({
  StatusLabel: ({ status }: { status: string }) => <span data-testid="status-label">{status}</span>,
}))

vi.mock('../../components/labels/ApprovalPendingBadge', () => ({
  ApprovalPendingBadge: ({ approvalPending }: { approvalPending?: boolean }) =>
    approvalPending ? <span data-testid="approval-pending-badge">Pending approval</span> : null,
}))

vi.mock('../../utils/dateUtils', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../utils/dateUtils')>()
  return {
    ...actual,
    formatElapsedTime: (ms: number) => `${ms}ms`,
  }
})

vi.mock('date-fns', async (importOriginal) => {
  const actual = await importOriginal<typeof import('date-fns')>()
  return {
    ...actual,
    isToday: () => true,
    isYesterday: () => false,
  }
})

vi.mock('../../components/table/PaginationFooter', () => ({
  PaginationFooter: ({ total, perPage }: { total: number; perPage: number }) => (
    <div data-testid="pagination-footer">{`1 - ${perPage} of ${total}`}</div>
  ),
}))

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

const baseExecution: Execution = {
  id: '12345678-abcd-ef01-2345-678901234567',
  workflow_id: 'wf-1',
  workflow_version_id: 'wfv-1',
  project_id: 'project-1',
  temporal_workflow_id: 'temporal-wf-1',
  status: 'running',
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-01-15T10:00:00Z',
  created_by: 'user-1',
  updated_by: null,
  completed_at: null,
  input_data: {},
  error_details: null,
}

describe('WorkflowHistoryCard', () => {
  const mockOnClose = vi.fn()
  const mockOnExecutionSelect = vi.fn()

  const defaultProps = {
    executions: [],
    onClose: mockOnClose,
    onExecutionSelect: mockOnExecutionSelect,
  }

  function renderCard(ui: React.ReactElement) {
    return render(ui, { wrapper: TestWrapper })
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the component with title', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} />)
    expect(screen.getByText('Run history')).toBeInTheDocument()
  })

  it('renders the subtext', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} />)
    expect(screen.getByText('View past runs of this workflow.')).toBeInTheDocument()
  })

  it('renders close button', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} />)
    expect(screen.getByLabelText('Close run history')).toBeInTheDocument()
  })

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup()
    renderCard(<WorkflowHistoryCard {...defaultProps} />)
    await user.click(screen.getByLabelText('Close run history'))
    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('shows empty message when no executions', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} />)
    expect(screen.getByText('No execution history available')).toBeInTheDocument()
  })

  it('renders date group header "Today" for a recent execution', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} executions={[baseExecution]} />)
    expect(screen.getByText('Today')).toBeInTheDocument()
  })

  it('renders execution rows with formatted date and status', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} executions={[baseExecution]} />)
    expect(screen.getByText(/Jan 15, 2024/)).toBeInTheDocument()
    expect(screen.getByTestId('status-label')).toHaveTextContent('running')
  })

  it('renders truncated run ID with label', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} executions={[baseExecution]} />)
    expect(screen.getByText('Run ID: 12345678')).toBeInTheDocument()
  })

  it('renders elapsed time when created_at and completed_at are present', () => {
    const execution: Execution = {
      ...baseExecution,
      created_at: '2024-01-15T10:00:00Z',
      completed_at: '2024-01-15T10:01:30Z',
    }
    renderCard(<WorkflowHistoryCard {...defaultProps} executions={[execution]} />)
    expect(screen.getByText('Elapsed time: 90000ms')).toBeInTheDocument()
  })

  it('renders "Elapsed time: -" when execution is completed with no timing data', () => {
    const execution: Execution = { ...baseExecution, status: 'completed' }
    renderCard(<WorkflowHistoryCard {...defaultProps} executions={[execution]} />)
    expect(screen.getByText('Elapsed time: -')).toBeInTheDocument()
  })

  it('renders multiple execution rows', () => {
    const executions: Execution[] = [
      { ...baseExecution, id: 'aaaaaaaa-0000-0000-0000-000000000001', status: 'completed' },
      { ...baseExecution, id: 'bbbbbbbb-0000-0000-0000-000000000002', status: 'failed' },
    ]
    renderCard(<WorkflowHistoryCard {...defaultProps} executions={executions} />)
    const statusLabels = screen.getAllByTestId('status-label')
    expect(statusLabels).toHaveLength(2)
    expect(statusLabels[0]).toHaveTextContent('completed')
    expect(statusLabels[1]).toHaveTextContent('failed')
  })

  it('calls onExecutionSelect with the execution id when row is clicked', async () => {
    const user = userEvent.setup()
    renderCard(<WorkflowHistoryCard {...defaultProps} executions={[baseExecution]} />)
    const row = screen.getByRole('button', { name: /running/i })
    await user.click(row)
    expect(mockOnExecutionSelect).toHaveBeenCalledWith(baseExecution.id)
  })

  it('highlights the selected execution row with pf-m-current class', () => {
    renderCard(
      <WorkflowHistoryCard {...defaultProps} executions={[baseExecution]} selectedExecutionId={baseExecution.id} />
    )
    const buttons = screen.getAllByRole('button')
    const rowButton = buttons.find((btn) => btn.textContent?.includes('Jan 15, 2024'))!
    expect(rowButton).toHaveClass('pf-m-current')
  })

  it('does not highlight an unselected row', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} executions={[baseExecution]} selectedExecutionId="other-id" />)
    const rowButton = screen.getByRole('button', { name: /running/i })
    expect(rowButton).not.toHaveClass('pf-m-current')
  })

  it('renders a SimpleList when executions are present', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} executions={[baseExecution]} />)
    expect(screen.getByRole('list')).toBeInTheDocument()
  })

  it('does not render sort column headers', () => {
    renderCard(<WorkflowHistoryCard {...defaultProps} />)
    expect(screen.queryByRole('columnheader', { name: /Started/i })).not.toBeInTheDocument()
  })

  describe('status filter', () => {
    it('renders filter bar when onFilterChange is provided', () => {
      const onFilterChange = vi.fn()
      renderCard(<WorkflowHistoryCard {...defaultProps} filters={[]} onFilterChange={onFilterChange} />)
      expect(screen.getByText('Filter by status')).toBeInTheDocument()
    })

    it('does not render filter bar when onFilterChange is not provided', () => {
      renderCard(<WorkflowHistoryCard {...defaultProps} />)
      expect(screen.queryByText('Status')).not.toBeInTheDocument()
    })

    it('shows status options from API contract when filter dropdown is opened', async () => {
      const user = userEvent.setup()
      const onFilterChange = vi.fn()
      renderCard(<WorkflowHistoryCard {...defaultProps} filters={[]} onFilterChange={onFilterChange} />)

      // Open the filter value dropdown (second dropdown in attribute-search)
      const statusToggle = screen.getByText('Filter by status')
      await user.click(statusToggle)

      expect(screen.getByText('Pending')).toBeInTheDocument()
      expect(screen.getByText('Running')).toBeInTheDocument()
      expect(screen.getByText('Paused')).toBeInTheDocument()
      expect(screen.getByText('Completed')).toBeInTheDocument()
      expect(screen.getByText('Failed')).toBeInTheDocument()
      expect(screen.getByText('Cancelled')).toBeInTheDocument()
    })

    it('calls onFilterChange when a status is selected', async () => {
      const user = userEvent.setup()
      const onFilterChange = vi.fn()
      renderCard(<WorkflowHistoryCard {...defaultProps} filters={[]} onFilterChange={onFilterChange} />)

      const statusToggle = screen.getByText('Filter by status')
      await user.click(statusToggle)
      await user.click(screen.getByText('Completed'))

      expect(onFilterChange).toHaveBeenCalledWith(
        expect.arrayContaining([expect.objectContaining({ key: 'status', value: 'completed' })])
      )
    })
  })

  it('shows empty filter state when filters are active and there are no executions', () => {
    const onFilterChange = vi.fn()
    renderCard(
      <WorkflowHistoryCard
        {...defaultProps}
        executions={[]}
        filters={[{ key: 'status', operator: 'eq', value: 'failed' }]}
        onFilterChange={onFilterChange}
      />
    )

    expect(screen.getByRole('button', { name: /clear all filters/i })).toBeInTheDocument()
  })

  it('shows empty filter state without a clear action when onFilterChange is omitted', () => {
    renderCard(
      <WorkflowHistoryCard
        {...defaultProps}
        executions={[]}
        filters={[{ key: 'status', operator: 'eq', value: 'failed' }]}
        onFilterChange={undefined}
      />
    )

    expect(screen.queryByRole('button', { name: /clear all filters/i })).not.toBeInTheDocument()
  })

  describe('pagination', () => {
    const mockOnPrev = vi.fn()
    const mockOnNext = vi.fn()
    const mockOnPerPageChange = vi.fn()

    it('renders pagination footer when paginationFooterProps is provided', () => {
      const paginationFooterProps = {
        page: 1,
        perPage: 20,
        total: 50,
        hasNext: true,
        onPrev: mockOnPrev,
        onNext: mockOnNext,
        onPerPageChange: mockOnPerPageChange,
      }

      renderCard(
        <WorkflowHistoryCard
          {...defaultProps}
          executions={[baseExecution]}
          paginationFooterProps={paginationFooterProps}
        />
      )

      expect(screen.getByTestId('pagination-footer')).toBeInTheDocument()
      expect(screen.getByText('1 - 20 of 50')).toBeInTheDocument()
    })

    it('does not render pagination footer when paginationFooterProps is not provided', () => {
      renderCard(<WorkflowHistoryCard {...defaultProps} executions={[baseExecution]} />)
      expect(screen.queryByTestId('pagination-footer')).not.toBeInTheDocument()
    })

    it('pagination footer is sticky at bottom with proper styling', () => {
      const paginationFooterProps = {
        page: 1,
        perPage: 20,
        total: 25,
        hasNext: true,
        onPrev: mockOnPrev,
        onNext: mockOnNext,
        onPerPageChange: mockOnPerPageChange,
      }

      renderCard(
        <WorkflowHistoryCard
          {...defaultProps}
          executions={[baseExecution]}
          paginationFooterProps={paginationFooterProps}
        />
      )

      // Footer should be rendered
      expect(screen.getByTestId('pagination-footer')).toBeInTheDocument()
      expect(screen.getByText('1 - 20 of 25')).toBeInTheDocument()
    })
  })
})

describe('ExecutionHistoryRow', () => {
  const mockOnSelect = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  function renderRow(execution: Execution, isSelected?: boolean) {
    return render(
      <SimpleList isControlled={false}>
        <ExecutionHistoryRow execution={execution} onSelect={mockOnSelect} isSelected={isSelected} />
      </SimpleList>,
      { wrapper: TestWrapper }
    )
  }

  it('renders formatted date in Mon D, YYYY format for an execution with created_at', () => {
    renderRow(baseExecution)
    expect(screen.getByText(/Jan 15, 2024/)).toBeInTheDocument()
  })

  it('does not render date when created_at is missing', () => {
    const execution = { ...baseExecution, created_at: undefined } as unknown as Execution
    renderRow(execution)
    expect(screen.queryByText(/2024/)).not.toBeInTheDocument()
  })

  it('renders elapsed time label when created_at and completed_at are present', () => {
    const execution: Execution = {
      ...baseExecution,
      created_at: '2024-01-15T10:00:00Z',
      completed_at: '2024-01-15T10:01:30Z',
    }
    renderRow(execution)
    expect(screen.getByText('Elapsed time: 90000ms')).toBeInTheDocument()
  })

  it('renders "Elapsed time: -" when execution is completed with no timing data', () => {
    renderRow({ ...baseExecution, status: 'completed' })
    expect(screen.getByText('Elapsed time: -')).toBeInTheDocument()
  })

  it('renders run ID with label', () => {
    renderRow(baseExecution)
    expect(screen.getByText('Run ID: 12345678')).toBeInTheDocument()
  })

  it('renders status label', () => {
    renderRow(baseExecution)
    expect(screen.getByTestId('status-label')).toHaveTextContent('running')
  })

  it('does not render status label when status is undefined', () => {
    const execution = { ...baseExecution, status: undefined } as unknown as Execution
    renderRow(execution)
    expect(screen.queryByTestId('status-label')).not.toBeInTheDocument()
  })

  it('calls onSelect when row is clicked', async () => {
    const user = userEvent.setup()
    renderRow(baseExecution)
    await user.click(screen.getByRole('button'))
    expect(mockOnSelect).toHaveBeenCalledTimes(1)
  })

  it('applies pf-m-current class when isSelected is true', () => {
    renderRow(baseExecution, true)
    expect(screen.getByRole('button')).toHaveClass('pf-m-current')
  })

  it('does not apply pf-m-current class when isSelected is false', () => {
    renderRow(baseExecution, false)
    expect(screen.getByRole('button')).not.toHaveClass('pf-m-current')
  })

  it('uses within to check layout structure', () => {
    renderRow(baseExecution)
    const row = screen.getByRole('button')
    expect(within(row).getByText(/Jan 15, 2024/)).toBeInTheDocument()
    expect(within(row).getByText('Run ID: 12345678')).toBeInTheDocument()
  })

  it('displays version publish name when available', () => {
    renderRow({
      ...baseExecution,
      workflow_version: 3,
      workflow_version_name: 'prod release',
    })
    expect(screen.getByText(/prod release/)).toBeInTheDocument()
  })

  it('displays version creation date when no publish name', () => {
    renderRow({
      ...baseExecution,
      workflow_version: 2,
      workflow_version_name: null,
      workflow_version_created_at: '2024-06-15T14:30:00Z',
    })
    expect(screen.getByText(/Version:/)).toBeInTheDocument()
  })

  it('links version to workflow builder with version param', () => {
    renderRow({
      ...baseExecution,
      workflow_version: 5,
      workflow_version_name: 'v5 release',
    })
    const link = screen.getByRole('link', { name: /v5 release/ })
    expect(link).toHaveAttribute('href', '/workflow-builder/wf-1?version=5')
  })

  it('does not display version when workflow_version is null', () => {
    renderRow({ ...baseExecution, workflow_version: undefined })
    expect(screen.queryByText(/Version:/)).not.toBeInTheDocument()
  })

  it('does not display version when workflow_id is missing', () => {
    renderRow({ ...baseExecution, workflow_version: 5, workflow_id: undefined as unknown as string })
    expect(screen.queryByText(/Version:/)).not.toBeInTheDocument()
  })

  it('does not render run id when execution id is missing', () => {
    renderRow({ ...baseExecution, id: undefined as unknown as string })
    expect(screen.queryByText(/Run ID:/)).not.toBeInTheDocument()
  })

  it('renders approval pending badge when approval_pending is true', () => {
    const execution: Execution = { ...baseExecution, approval_pending: true }
    renderRow(execution)
    expect(screen.getByTestId('approval-pending-badge')).toBeInTheDocument()
    expect(screen.getByText('Pending approval')).toBeInTheDocument()
  })

  it('does not render approval pending badge when approval_pending is false', () => {
    const execution: Execution = { ...baseExecution, approval_pending: false }
    renderRow(execution)
    expect(screen.queryByTestId('approval-pending-badge')).not.toBeInTheDocument()
  })

  it('does not render approval pending badge when approval_pending is undefined', () => {
    renderRow(baseExecution)
    expect(screen.queryByTestId('approval-pending-badge')).not.toBeInTheDocument()
  })

  it('renders "Test run" label when execution_metadata.mode is "test"', () => {
    const testExecution = {
      ...baseExecution,
      execution_metadata: { mode: 'test' },
    } as Execution
    renderRow(testExecution)
    expect(screen.getByText('Test run')).toBeInTheDocument()
  })

  it('does not render "Test run" label when execution_metadata.mode is not "test"', () => {
    const normalExecution = {
      ...baseExecution,
      execution_metadata: { mode: 'normal' },
    } as Execution
    renderRow(normalExecution)
    expect(screen.queryByText('Test run')).not.toBeInTheDocument()
  })

  it('does not render "Test run" label when execution_metadata is undefined', () => {
    renderRow(baseExecution)
    expect(screen.queryByText('Test run')).not.toBeInTheDocument()
  })

  it('renders all badges together for a test run with pending approval', () => {
    const execution = {
      ...baseExecution,
      approval_pending: true,
      execution_metadata: { mode: 'test' },
    } as Execution
    renderRow(execution)
    expect(screen.getByTestId('approval-pending-badge')).toBeInTheDocument()
    expect(screen.getByText('Test run')).toBeInTheDocument()
  })

  it('anchors the kebab menu with the timestamp for retryable executions', () => {
    renderRow({ ...baseExecution, status: 'failed' })

    expect(screen.getByRole('button', { name: /Actions for execution/ })).toBeInTheDocument()
    expect(screen.getByText(/Jan 15, 2024/)).toBeInTheDocument()
    expect(screen.getByTestId('status-label')).toHaveTextContent('failed')
  })

  it('does not render the kebab for non-retryable running executions', () => {
    renderRow({ ...baseExecution, status: 'running' })

    expect(screen.queryByRole('button', { name: /Actions for execution/ })).not.toBeInTheDocument()
  })

  it('passes resourceProject to useCanI for retryable executions', () => {
    renderRow({ ...baseExecution, status: 'failed', project_id: 'proj-abc' })

    expect(useCanI).toHaveBeenCalledWith('run', 'execution', { resourceProject: 'proj-abc' })
  })

  it('opens the retry dialog from the kebab menu', async () => {
    const user = userEvent.setup()
    renderRow({ ...baseExecution, status: 'failed' })

    await user.click(screen.getByRole('button', { name: /Actions for execution/ }))
    await user.click(screen.getByText('Retry run'))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders retried-from metadata when present', () => {
    renderRow({
      ...baseExecution,
      status: 'completed',
      retried_from_execution_id: 'abcdef12-3456-7890-abcd-ef1234567890',
    })

    expect(screen.getByText('Retried from: abcdef12')).toBeInTheDocument()
  })
})
