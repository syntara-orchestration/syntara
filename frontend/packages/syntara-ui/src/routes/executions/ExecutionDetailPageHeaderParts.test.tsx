import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { axe } from 'vitest-axe'

import { useCanI } from '../../hooks/useCanI'

import { ExecutionDetailHeaderToolbar, ExecutionDetailTitleRowAddons } from './ExecutionDetailPageHeaderParts'
import { executionDetailHasTitleRowExtras, executionDetailPageHeading } from './executionDetailPageHeaderTitle'

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
  executionsClient: {
    useMutation: vi.fn(() => ({
      mutate: vi.fn(),
      isPending: false,
    })),
  },
  workflowClient: {
    useQuery: vi.fn(() => ({
      data: null,
      isLoading: false,
      error: null,
    })),
  },
}))

vi.mock('../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
  }),
}))

beforeEach(() => {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('executionDetailPageHeaderTitle', () => {
  it('derives heading from workflow metadata when present', () => {
    const execution = {
      workflow_definition: { metadata: { name: 'My workflow' } },
    } as unknown as Parameters<typeof executionDetailPageHeading>[0]
    expect(executionDetailPageHeading(execution, 'exec-id')).toBe('My workflow')
  })

  it('falls back to top-level name when metadata.name is missing', () => {
    const execution = {
      workflow_definition: { name: 'Top-level name' },
    } as unknown as Parameters<typeof executionDetailPageHeading>[0]
    expect(executionDetailPageHeading(execution, 'exec-id')).toBe('Top-level name')
  })

  it('falls back to execution id prefix when metadata missing', () => {
    expect(executionDetailPageHeading(undefined, 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')).toBe('Execution aaaaaaaa...')
  })

  it('detects when title row extras should render', () => {
    expect(executionDetailHasTitleRowExtras(undefined)).toBe(false)
  })
})

describe('ExecutionDetailPageHeaderParts', () => {
  it('renders no addon labels when execution has no status or created time', () => {
    render(<ExecutionDetailTitleRowAddons execution={undefined} />)
    expect(screen.queryByText(/Viewing run/i)).not.toBeInTheDocument()
  })

  it('has no accessibility violations for title row addons with status', async () => {
    const execution = {
      status: 'running' as const,
      created_at: '2024-01-01T00:00:00.000Z',
    } as never
    const { container } = render(<ExecutionDetailTitleRowAddons execution={execution} />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('has no accessibility violations for header toolbar', async () => {
    const queryClient = new QueryClient()
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={false}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={false}
          executionId="exec-123"
          execution={undefined}
        />
      </QueryClientProvider>
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('renders cancel button when execution is cancellable', () => {
    const queryClient = new QueryClient()
    const execution = {
      id: 'exec-123',
      workflow_id: 'wf-1',
      workflow_version_id: 'wfv-1',
      project_id: 'proj-1',
      status: 'running' as const,
    } as never
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={false}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={true}
          executionId="exec-123"
          execution={execution}
        />
      </QueryClientProvider>
    )
    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeInTheDocument()
  })

  it('does not render cancel button when execution is undefined even if isCancellable', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={false}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={true}
          executionId="exec-123"
          execution={undefined}
        />
      </QueryClientProvider>
    )
    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
  })

  it('does not render cancel button when execution is not cancellable', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={false}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={false}
          executionId="exec-123"
          execution={undefined}
        />
      </QueryClientProvider>
    )
    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
  })

  it('renders status label when execution has status', () => {
    const execution = {
      status: 'running' as const,
    } as never
    render(<ExecutionDetailTitleRowAddons execution={execution} />)
    expect(screen.getByText('Running')).toBeInTheDocument()
  })

  it('renders viewing run label when execution has created_at', () => {
    const execution = {
      created_at: '2024-01-15T10:30:00.000Z',
    } as never
    render(<ExecutionDetailTitleRowAddons execution={execution} />)
    expect(screen.getByText(/Viewing run:/)).toBeInTheDocument()
  })

  it('renders approval action buttons when showApprovalActionStrip is true', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={true}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={false}
          executionId="exec-123"
          execution={undefined}
        />
      </QueryClientProvider>
    )
    expect(screen.getByRole('button', { name: /Review/i })).toBeInTheDocument()
  })

  it('renders cancel and approval buttons together when both applicable', () => {
    const queryClient = new QueryClient()
    const execution = {
      id: 'exec-123',
      workflow_id: 'wf-1',
      workflow_version_id: 'wfv-1',
      project_id: 'proj-1',
      status: 'running' as const,
    } as never
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={true}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={true}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={true}
          executionId="exec-123"
          execution={execution}
        />
      </QueryClientProvider>
    )
    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Review/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to editor' })).toBeInTheDocument()
  })

  it('renders copy to editor button', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={false}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={false}
          executionId="exec-123"
          execution={undefined}
        />
      </QueryClientProvider>
    )
    expect(screen.getByRole('button', { name: 'Copy to editor' })).toBeInTheDocument()
  })

  it('calls onCopyToEditor when copy to editor button is clicked', async () => {
    const queryClient = new QueryClient()
    const onCopyToEditor = vi.fn()
    const user = (await import('@testing-library/user-event')).default.setup()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={false}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={onCopyToEditor}
          isCancellable={false}
          executionId="exec-123"
          execution={undefined}
        />
      </QueryClientProvider>
    )
    await user.click(screen.getByRole('button', { name: 'Copy to editor' }))
    expect(onCopyToEditor).toHaveBeenCalledOnce()
  })

  it('passes resourceProject to useCanI for cancel and retry buttons', () => {
    const queryClient = new QueryClient()
    const execution = {
      id: 'exec-scoped',
      workflow_id: 'wf-1',
      workflow_version_id: 'wfv-1',
      project_id: 'proj-42',
      status: 'failed' as const,
      mode: 'standard',
    } as never
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={false}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={false}
          executionId="exec-scoped"
          execution={execution}
        />
      </QueryClientProvider>
    )

    expect(useCanI).toHaveBeenCalledWith('run', 'execution', { resourceProject: 'proj-42' })
  })

  it('renders retry button when execution is in terminal state', () => {
    const queryClient = new QueryClient()
    const execution = {
      id: 'exec-terminal',
      workflow_id: 'wf-1',
      workflow_version_id: 'wfv-1',
      project_id: 'proj-1',
      status: 'failed' as const,
      mode: 'standard',
    } as never
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={false}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={false}
          executionId="exec-terminal"
          execution={execution}
        />
      </QueryClientProvider>
    )
    expect(screen.getByRole('button', { name: 'Retry run' })).toBeInTheDocument()
  })

  it('does not render retry button for running execution', () => {
    const queryClient = new QueryClient()
    const execution = {
      id: 'exec-running',
      workflow_id: 'wf-1',
      workflow_version_id: 'wfv-1',
      project_id: 'proj-1',
      status: 'running' as const,
      mode: 'standard',
    } as never
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetailHeaderToolbar
          showApprovalActionStrip={false}
          isApprovalLoading={false}
          onReviewClick={() => {}}
          historyCardOpen={false}
          onToggleHistory={() => {}}
          onBackToEditor={() => {}}
          onCopyToEditor={() => {}}
          isCancellable={true}
          executionId="exec-running"
          execution={execution}
        />
      </QueryClientProvider>
    )
    expect(screen.queryByRole('button', { name: 'Retry run' })).not.toBeInTheDocument()
  })

  it('renders both status and viewing run label when execution has both', () => {
    const execution = {
      status: 'completed' as const,
      created_at: '2024-01-15T10:30:00.000Z',
    } as never
    render(<ExecutionDetailTitleRowAddons execution={execution} />)
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText(/Viewing run:/)).toBeInTheDocument()
  })

  it('renders ApprovalPendingBadge when execution has approval_pending', () => {
    const execution = {
      status: 'running' as const,
      approval_pending: true,
    } as never
    render(<ExecutionDetailTitleRowAddons execution={execution} />)
    expect(screen.getByText('Pending approval')).toBeInTheDocument()
  })
})
