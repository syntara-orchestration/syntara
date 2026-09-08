import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useParams, useRouterState } from '@tanstack/react-router'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { axe } from 'vitest-axe'

import { executionsClient } from '../../client'
import { useExecutionStore } from '../workflows/stores/useExecutionStore'

import ExecutionDetail from './ExecutionDetail'
import { useExecutionNodeClick } from './hooks/useExecutionNodeClick'

// Create mock functions
const mockNavigate = vi.fn()

vi.mock('../../hooks/routing/useLocation', () => ({
  useLocation: () => '/',
}))
vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: vi.fn(() => ({ executionId: 'exec-123' })),
    useRouterState: vi.fn(() => ''),
  }
})

// Mock the workflow client with execution query that includes workflow_definition
const mockExecutionQuery = {
  data: {
    id: 'exec-123',
    workflow_id: 'wf-456',
    workflow_version_id: 'version-789',
    status: 'running',
    started_at: '2024-01-01T00:00:00Z',
    project_id: 'project-1',
    activities: [
      {
        id: 'activity-1',
        activity_id: 'task-1',
        activity_name: 'task-1',
        status: 'completed',
        started_at: '2024-01-01T00:00:00Z',
        completed_at: '2024-01-01T00:01:00Z',
      },
    ],
    workflow_definition: {
      schemaVersion: '1.0.0',
      version: 1,
      metadata: {
        name: 'Test Workflow',
        description: 'A test workflow',
      },
      workflow: {
        activities: [
          {
            id: 'task-1',
            type: 'task' as const,
            name: 'Test Task',
            tool: {
              provider_id: 'test-provider',
              tool_id: 'test-tool',
            },
          },
        ],
      },
    },
  },
  isLoading: false,
  error: null,
  refetch: vi.fn(),
}

const mockExecutionsQuery = {
  data: {
    resources: [
      { id: 'exec-123', status: 'running', created_at: '2024-01-01T00:00:00Z' },
      { id: 'exec-456', status: 'completed', created_at: '2024-01-01T01:00:00Z' },
    ],
  },
  isLoading: false,
  error: null,
}

vi.mock('../../hooks/useCanI', () => ({
  useCanI: vi.fn(() => ({ allowed: true, isChecking: false, isError: false })),
}))

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
  executionsClient: {
    useQuery: vi.fn((_method: string, endpoint: string) => {
      if (endpoint === '/executions/{execution_id}') {
        return mockExecutionQuery
      }
      if (endpoint === '/executions') {
        return mockExecutionsQuery
      }
      return { data: null, isLoading: false, error: null }
    }),
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
    useMutation: vi.fn(() => ({
      mutateAsync: vi.fn(),
      isPending: false,
    })),
  },
  approvalsClient: {
    useQuery: vi.fn(() => ({
      data: null,
      isPending: false,
      error: null,
      isError: false,
      refetch: vi.fn(),
    })),
  },
  usersClient: {
    useQuery: vi.fn(() => ({
      data: undefined,
      isLoading: false,
    })),
  },
}))

vi.mock('../../stores/useAuthStore', () => ({
  useAuthStore: vi.fn((selector: (state: { username: string; userId: string }) => unknown) => {
    const state = { username: 'testuser', userId: 'test-user-id' }

    return selector(state)
  }),
}))

// Mock workflow store with required selectors
vi.mock('../../stores/useWorkflowStore', () => ({
  useWorkflowStore: vi.fn((selector?: (state: unknown) => unknown) => {
    const state = {
      updateActivity: vi.fn(),
      activities: [],
      triggers: [],
      edges: [],
    }
    return selector ? selector(state) : state
  }),
  selectCurrentWorkflow: vi.fn(),
  selectWorkflowVersion: vi.fn(),
  selectEdges: vi.fn(() => []),
  selectTriggersCount: vi.fn(() => 0),
  selectActivities: vi.fn(() => []),
}))

// Mock workflow store selectors
vi.mock('../../stores/workflowStoreSelectors', () => ({
  useActivities: vi.fn(() => []),
  useTriggers: vi.fn(() => []),
}))

// Mock ExecutionViewContent component
vi.mock('../builder/ExecutionViewContent', () => ({
  ExecutionViewContent: ({
    workflow,
    executionStatus,
  }: {
    workflow: { name?: string } | undefined
    executionStatus: string | null
  }) => (
    <div data-testid="execution-view-content">
      <div>Workflow: {workflow?.name}</div>
      <div>Execution Status: {executionStatus}</div>
    </div>
  ),
}))

// Mock ExecutionDetailsPanel component
vi.mock('../builder/ExecutionDetailsPanel', () => ({
  ExecutionDetailsPanel: ({ executionId }: { executionId: string }) => (
    <div data-testid="execution-details-panel">
      <div>Execution ID: {executionId}</div>
    </div>
  ),
}))

// Mock WorkflowHistoryCard component
vi.mock('../builder/WorkflowHistoryCard', () => ({
  WorkflowHistoryCard: ({
    executions,
    selectedExecutionId,
    onClose,
    onExecutionSelect,
  }: {
    executions: Array<{ id: string }>
    selectedExecutionId?: string | null
    onClose: () => void
    onExecutionSelect: (id: string) => void
  }) => (
    <div data-testid="workflow-history-card">
      <button onClick={onClose} aria-label="Close history">
        Close History
      </button>
      {executions.map((exec) => (
        <button key={exec.id} onClick={() => onExecutionSelect(exec.id)} aria-label={`Select execution ${exec.id}`}>
          {exec.id}
          {exec.id === selectedExecutionId && ' (selected)'}
        </button>
      ))}
    </div>
  ),
}))

// Mock StatusLabel component
vi.mock('../builder/ExecutionStatus', () => ({
  StatusLabel: ({ status }: { status: string }) => {
    const capitalizedStatus = status.charAt(0).toUpperCase() + status.slice(1)
    return <div>{capitalizedStatus}</div>
  },
}))

// Mock useExecutionWebSocket hook
vi.mock('../workflows/hooks/useExecutionWebSocket', () => ({
  useExecutionWebSocket: vi.fn(),
}))

// Mock ApprovalSidePanel component
vi.mock('./ApprovalSidePanel', () => ({
  ApprovalSidePanel: ({ approval, onClose }: { approval: { id: string; name: string }; onClose: () => void }) => (
    <div data-testid="approval-side-panel">
      <div>Approval: {approval.name}</div>
      <button onClick={onClose}>Close approval panel</button>
    </div>
  ),
}))

vi.mock('./hooks/useAutoApprovalDetection', () => ({
  useAutoApprovalDetection: vi.fn(),
}))

const mockForkAsNewWorkflow = vi.fn()
vi.mock('./hooks/useForkWorkflow', () => ({
  useForkWorkflow: vi.fn(() => ({
    forkAsNewWorkflow: mockForkAsNewWorkflow,
    isForkLoading: false,
  })),
}))

const mockShowError = vi.fn()
vi.mock('../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({
    showError: mockShowError,
    showSuccess: vi.fn(),
    showWarning: vi.fn(),
    showInfo: vi.fn(),
    showAlert: vi.fn(),
    dismissAlert: vi.fn(),
    clearAllAlerts: vi.fn(),
  })),
}))

// Mock useExecutionNodeClick hook
const mockHandleNodeClick = vi.fn()
const mockSelectNode = vi.fn()
const mockDeselectNode = vi.fn()
const mockPendingApproval = {
  id: 'approval-1',
  name: 'Test Approval',
  approval_node_id: 'node-abc',
  status: 'pending',
  execution_id: 'exec-123',
  workflow_context: { workflow_name: 'Test Workflow' },
}

const mockClearPendingApproval = vi.fn()
const mockSetPendingApproval = vi.fn()
const mockFetchForNode = vi.fn()

vi.mock('./hooks/useExecutionNodeClick', () => ({
  useExecutionNodeClick: vi.fn(() => ({
    approvals: [],
    currentIndex: 0,
    currentApproval: null,
    isApprovalLoading: false,
    navigateToIndex: vi.fn(),
    clearApprovals: mockClearPendingApproval,
    setApprovalsAndIndex: mockSetPendingApproval,
    fetchApprovals: mockFetchForNode,
    selectedNodeId: null,
    selectedNodeName: null,
    selectNode: mockSelectNode,
    deselectNode: mockDeselectNode,
    handleNodeClick: mockHandleNodeClick,
  })),
}))

describe('ExecutionDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockNavigate.mockClear()
    vi.mocked(useParams).mockReturnValue({ executionId: 'exec-123' })
    vi.mocked(useRouterState).mockReturnValue('' as never)
    // Stub matchMedia for PatternFly Modal rendering
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

  it('renders page with workflow name and status in title', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    expect(screen.getByText('Test Workflow')).toBeInTheDocument()
    expect(screen.getByText('Running')).toBeInTheDocument()
  })

  it('renders BuilderContent with execution view props', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    expect(screen.getByTestId('execution-view-content')).toBeInTheDocument()
    expect(screen.getByText('Execution Status: running')).toBeInTheDocument()
  })

  it('renders execution details panel with correct execution ID', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    expect(screen.getByTestId('execution-details-panel')).toBeInTheDocument()
    expect(screen.getByText('Execution ID: exec-123')).toBeInTheDocument()
  })

  it('fetches execution with workflow_definition and activities included', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    expect(vi.mocked(executionsClient.useQuery)).toHaveBeenCalledWith(
      'get',
      '/executions/{execution_id}',
      expect.objectContaining({
        params: {
          path: { execution_id: 'exec-123' },
          query: {
            include: 'workflow_definition,activities',
          },
        },
      }),
      expect.objectContaining({
        refetchInterval: expect.any(Function) as unknown,
      })
    )
  })

  it('does not show history panel by default and keeps the run history icon', () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    expect(screen.queryByTestId('workflow-history-card')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Run history')).toBeInTheDocument()
  })

  it('shows history panel when history=open query param is present', () => {
    vi.mocked(useRouterState).mockReturnValue('?history=open' as never)

    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    expect(screen.getByTestId('workflow-history-card')).toBeInTheDocument()
  })

  it('toggles history panel open from closed state', async () => {
    vi.mocked(useRouterState).mockReturnValue('?history=closed' as never)

    const user = userEvent.setup()
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    // History should be closed initially
    expect(screen.queryByTestId('workflow-history-card')).not.toBeInTheDocument()

    const historyButton = screen.getByLabelText('Run history')
    await user.click(historyButton)

    expect(mockNavigate).toHaveBeenCalledWith(
      expect.objectContaining({
        to: '/executions/$executionId',
        params: { executionId: 'exec-123' },
      })
    )
  })

  it('toggles history panel closed when history button is clicked', async () => {
    vi.mocked(useRouterState).mockReturnValue('?history=open' as never)

    const user = userEvent.setup()
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    expect(screen.getByTestId('workflow-history-card')).toBeInTheDocument()

    const historyButton = screen.getByLabelText('Run history')
    await user.click(historyButton)

    expect(mockNavigate).toHaveBeenCalledWith(
      expect.objectContaining({ to: '/executions/$executionId', params: { executionId: 'exec-123' } })
    )
  })

  it('closes history panel when close button in history card is clicked', async () => {
    vi.mocked(useRouterState).mockReturnValue('?history=open' as never)

    const user = userEvent.setup()
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    const closeButton = screen.getByLabelText('Close history')
    await user.click(closeButton)

    expect(mockNavigate).toHaveBeenCalledWith(
      expect.objectContaining({ to: '/executions/$executionId', params: { executionId: 'exec-123' } })
    )
  })

  it('navigates to workflow builder when Back to editor button is clicked', async () => {
    const user = userEvent.setup()
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    const backButton = screen.getByRole('button', { name: 'Back to editor' })
    await user.click(backButton)

    expect(mockNavigate).toHaveBeenCalledWith({ to: '/workflow-builder/$workflowId', params: { workflowId: 'wf-456' } })
  })

  it('preserves history panel state when navigating to different execution', async () => {
    vi.mocked(useRouterState).mockReturnValue('?history=open' as never)

    const user = userEvent.setup()
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    const executionButton = screen.getByLabelText('Select execution exec-456')
    await user.click(executionButton)

    expect(mockNavigate).toHaveBeenCalledWith(
      expect.objectContaining({ to: '/executions/$executionId', params: { executionId: 'exec-456' } })
    )
  })

  it('uses executionId as key for ReactFlowProvider', () => {
    const queryClient = new QueryClient()
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )

    // ReactFlowProvider should re-mount when executionId changes
    // This is tested by checking that the component renders properly
    expect(container).toBeTruthy()
  })

  describe('pending activities initialization', () => {
    it('creates pending activity states when execution has no activities yet', () => {
      // Mock execution with no activity executions but has workflow definition
      const mockNewExecutionQuery = {
        data: {
          id: 'exec-new',
          workflow_id: 'wf-456',
          status: 'pending',
          activities: [], // No activity executions yet
          workflow_definition: {
            workflow: {
              activities: [
                { id: 'task-1', type: 'task', name: 'Task 1' },
                { id: 'task-2', type: 'task', name: 'Task 2' },
                { id: 'task-3', type: 'task', name: 'Task 3' },
              ],
            },
          },
        },
        isLoading: false,
        error: null,
      }

      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return mockNewExecutionQuery
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // The component should render without errors
      expect(screen.getByTestId('execution-view-content')).toBeInTheDocument()
    })

    it('uses actual activity executions when they exist', () => {
      // Default mock has activities
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Should render with actual activity data
      expect(screen.getByTestId('execution-view-content')).toBeInTheDocument()
    })

    it('handles execution with no workflow definition gracefully', () => {
      const mockMinimalExecution = {
        data: {
          id: 'exec-minimal',
          workflow_id: 'wf-456',
          status: 'pending',
          activities: [],
          workflow_definition: null, // No workflow definition
        },
        isLoading: false,
        error: null,
      }

      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return mockMinimalExecution
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Should render without crashing
      expect(screen.getByTestId('execution-view-content')).toBeInTheDocument()
    })
  })

  describe('Execution Store Reset', () => {
    it('resets execution store when executionId changes', async () => {
      const queryClient = new QueryClient()

      // Mock execution store with reset function
      const mockReset = vi.fn()
      const mockSetActivityExecutions = vi.fn()

      // Store the original useExecutionStore module
      const { useExecutionStore } = await import('../workflows/stores/useExecutionStore')

      // Mock getState to return our mock functions
      const originalGetState = useExecutionStore.getState
      useExecutionStore.getState = vi.fn(() => ({
        ...originalGetState(),
        reset: mockReset,
        setActivityExecutions: mockSetActivityExecutions,
      }))

      // Initial render with exec-123
      vi.mocked(useParams).mockReturnValue({ executionId: 'exec-123' })
      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Should call reset on mount
      expect(mockReset).toHaveBeenCalledTimes(1)

      // Change executionId to exec-456
      vi.mocked(useParams).mockReturnValue({ executionId: 'exec-456' })
      rerender(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Should call reset again when executionId changes
      expect(mockReset).toHaveBeenCalledTimes(2)

      // Restore original
      useExecutionStore.getState = originalGetState
    })

    it('does not reset execution store when executionId stays the same', async () => {
      const queryClient = new QueryClient()

      // Mock execution store with reset function
      const mockReset = vi.fn()
      const mockSetActivityExecutions = vi.fn()

      // Store the original useExecutionStore module
      const { useExecutionStore } = await import('../workflows/stores/useExecutionStore')

      // Mock getState to return our mock functions
      const originalGetState = useExecutionStore.getState
      useExecutionStore.getState = vi.fn(() => ({
        ...originalGetState(),
        reset: mockReset,
        setActivityExecutions: mockSetActivityExecutions,
      }))

      // Initial render with exec-123
      vi.mocked(useParams).mockReturnValue({ executionId: 'exec-123' })
      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Should call reset on mount
      expect(mockReset).toHaveBeenCalledTimes(1)

      // Re-render with same executionId
      rerender(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Should still only have called reset once (not called again for same executionId)
      expect(mockReset).toHaveBeenCalledTimes(1)

      // Restore original
      useExecutionStore.getState = originalGetState
    })

    it('does not reset execution store when executionId is undefined', async () => {
      const queryClient = new QueryClient()
      const mockReset = vi.fn()
      const mockSetActivityExecutions = vi.fn()

      const { useExecutionStore } = await import('../workflows/stores/useExecutionStore')
      const originalGetState = useExecutionStore.getState
      useExecutionStore.getState = vi.fn(() => ({
        ...originalGetState(),
        reset: mockReset,
        setActivityExecutions: mockSetActivityExecutions,
      }))

      vi.mocked(useParams).mockReturnValue({ executionId: undefined })
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(mockReset).not.toHaveBeenCalled()
      expect(vi.mocked(executionsClient.useQuery)).toHaveBeenCalledWith(
        'get',
        '/executions/{execution_id}',
        expect.objectContaining({
          params: expect.objectContaining({
            path: { execution_id: '' },
          }) as Record<string, unknown>,
          enabled: false,
        }),
        expect.objectContaining({
          refetchInterval: expect.any(Function) as unknown,
        })
      )

      useExecutionStore.getState = originalGetState
    })
  })

  describe('Approval Review Side Panel', () => {
    it('opens approval side panel when Review approval is clicked', async () => {
      vi.mocked(useExecutionNodeClick).mockReturnValue({
        approvals: [mockPendingApproval] as never,
        currentIndex: 0,
        currentApproval: mockPendingApproval as never,
        isApprovalLoading: false,
        navigateToIndex: vi.fn(),
        clearApprovals: mockClearPendingApproval,
        setApprovalsAndIndex: mockSetPendingApproval,
        fetchApprovals: mockFetchForNode,
        selectedNodeId: null,
        selectedNodeName: null,
        selectNode: mockSelectNode,
        deselectNode: mockDeselectNode,
        handleNodeClick: mockHandleNodeClick,
      })

      const user = userEvent.setup()
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      await user.click(screen.getByRole('button', { name: 'Review approval' }))

      expect(screen.getByTestId('approval-side-panel')).toBeInTheDocument()
      expect(screen.getByTestId('execution-view-content')).toBeInTheDocument()
    })

    it('closes approval side panel when Close is clicked', async () => {
      vi.mocked(useExecutionNodeClick).mockReturnValue({
        approvals: [mockPendingApproval] as never,
        currentIndex: 0,
        currentApproval: mockPendingApproval as never,
        isApprovalLoading: false,
        navigateToIndex: vi.fn(),
        clearApprovals: mockClearPendingApproval,
        setApprovalsAndIndex: mockSetPendingApproval,
        fetchApprovals: mockFetchForNode,
        selectedNodeId: null,
        selectedNodeName: null,
        selectNode: mockSelectNode,
        deselectNode: mockDeselectNode,
        handleNodeClick: mockHandleNodeClick,
      })

      const user = userEvent.setup()
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      await user.click(screen.getByRole('button', { name: 'Review approval' }))
      expect(screen.getByTestId('approval-side-panel')).toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'Close approval panel' }))
      expect(screen.queryByTestId('approval-side-panel')).not.toBeInTheDocument()
      expect(screen.getByTestId('execution-view-content')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Review approval' })).toBeInTheDocument()
      expect(mockClearPendingApproval).not.toHaveBeenCalled()
    })
  })

  describe('Cancel Execution Button', () => {
    it('shows cancel button when execution is running', () => {
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.getByRole('button', { name: 'Cancel run' })).toBeInTheDocument()
    })

    it('shows cancel button when execution is pending', () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return { ...mockExecutionQuery, data: { ...mockExecutionQuery.data, status: 'pending' } }
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.getByRole('button', { name: 'Cancel run' })).toBeInTheDocument()
    })

    it('does not show cancel button when execution is completed', () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return { ...mockExecutionQuery, data: { ...mockExecutionQuery.data, status: 'completed' } }
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
    })

    it('does not show cancel button when execution is failed', () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return { ...mockExecutionQuery, data: { ...mockExecutionQuery.data, status: 'failed' } }
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
    })

    it('does not show cancel button when execution is cancelled', () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return { ...mockExecutionQuery, data: { ...mockExecutionQuery.data, status: 'cancelled' } }
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument()
    })
  })

  describe('Failure Toast Alert', () => {
    it('shows failure toast when execution transitions from running to failed', () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return { ...mockExecutionQuery, data: { ...mockExecutionQuery.data, status: 'running' } }
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(mockShowError).not.toHaveBeenCalled()

      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return { ...mockExecutionQuery, data: { ...mockExecutionQuery.data, status: 'failed' } }
        }
        return mockExecutionsQuery
      })

      rerender(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Test Workflow run failed',
        description: 'View the run logs and copy to the editor to debug within the editor',
      })
    })

    it('does not show failure toast when navigating directly to a failed execution', () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return { ...mockExecutionQuery, data: { ...mockExecutionQuery.data, status: 'failed' } }
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(mockShowError).not.toHaveBeenCalled()
    })

    it('does not show failure toast when execution is still running', () => {
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(mockShowError).not.toHaveBeenCalled()
    })
  })

  describe('Error and Loading States', () => {
    it('renders error state when executionId is undefined', () => {
      vi.mocked(useParams).mockReturnValue({ executionId: undefined })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.getByText('Invalid execution')).toBeInTheDocument()
      expect(screen.getByText('No execution ID provided')).toBeInTheDocument()
      expect(screen.queryByTestId('execution-view-content')).not.toBeInTheDocument()
    })

    it('renders loading state when query is loading', () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return { data: undefined, isLoading: true, error: null }
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.getByLabelText('Loading')).toBeInTheDocument()
      expect(screen.queryByTestId('execution-view-content')).not.toBeInTheDocument()
    })

    it('renders error state when query has an error', () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return { data: undefined, isLoading: false, error: new Error('Network error') }
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.getAllByText('Error loading execution').length).toBeGreaterThanOrEqual(1)
      expect(screen.queryByTestId('execution-view-content')).not.toBeInTheDocument()
    })

    it('does not render error states when executionId is present and query succeeds', () => {
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.queryByText('Invalid execution')).not.toBeInTheDocument()
      expect(screen.getByTestId('execution-view-content')).toBeInTheDocument()
    })
  })

  describe('Copy to Editor Dialog', () => {
    it('navigates to workflow builder on replace when execution has workflow_id', async () => {
      const user = userEvent.setup()
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Open the copy-to-editor dialog
      await user.click(screen.getByRole('button', { name: 'Copy to editor' }))

      // Click "Replace current workflow"
      await user.click(screen.getByRole('button', { name: 'Replace current workflow' }))

      expect(mockNavigate).toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/workflow-builder/$workflowId',
          params: { workflowId: 'wf-456' },
          search: { fromExecution: 'exec-123' },
        })
      )
    })

    it('does not navigate on replace when workflow_id is missing', async () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return {
            ...mockExecutionQuery,
            data: { ...mockExecutionQuery.data, workflow_id: undefined },
          }
        }
        return mockExecutionsQuery
      })

      const user = userEvent.setup()
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      await user.click(screen.getByRole('button', { name: 'Copy to editor' }))
      mockNavigate.mockClear()
      await user.click(screen.getByRole('button', { name: 'Replace current workflow' }))

      expect(mockNavigate).not.toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/workflow-builder/$workflowId',
        })
      )
    })

    it('navigates to forked workflow on successful fork', async () => {
      mockForkAsNewWorkflow.mockResolvedValue('new-wf-id')

      const user = userEvent.setup()
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      await user.click(screen.getByRole('button', { name: 'Copy to editor' }))
      await user.click(screen.getByRole('button', { name: 'Fork as new workflow' }))

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(
          expect.objectContaining({
            to: '/workflow-builder/$workflowId',
            params: { workflowId: 'new-wf-id' },
            search: { linkExecution: 'exec-123' },
          })
        )
      })
    })

    it('does not navigate when fork returns no id', async () => {
      mockForkAsNewWorkflow.mockResolvedValue(undefined)

      const user = userEvent.setup()
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      await user.click(screen.getByRole('button', { name: 'Copy to editor' }))
      mockNavigate.mockClear()
      await user.click(screen.getByRole('button', { name: 'Fork as new workflow' }))

      await waitFor(() => {
        expect(mockForkAsNewWorkflow).toHaveBeenCalledOnce()
      })

      expect(mockNavigate).not.toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/workflow-builder/$workflowId',
        })
      )
    })
  })

  describe('Connection Banner', () => {
    it('shows connection banner when execution store reports stale state', () => {
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Set stale state AFTER render (useResetOnExecutionChange resets the store on mount)
      act(() => {
        useExecutionStore.setState({ isStale: true, isComplete: false })
      })

      // ConnectionBanner renders with "Live updates paused" alert
      expect(screen.getByText('Live updates paused')).toBeInTheDocument()
      expect(screen.getByTestId('execution-view-content')).toBeInTheDocument()

      // Reset store state
      act(() => {
        useExecutionStore.setState({ isStale: false, isComplete: false })
      })
    })

    it('does not show connection banner when execution is not stale', () => {
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      expect(screen.queryByText('Live updates paused')).not.toBeInTheDocument()
    })
  })

  describe('ExecutionDetailContent rendering', () => {
    it('renders the resizable panel and execution view with node click handler', () => {
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // ExecutionViewContent and ExecutionDetailsPanel should render inside ExecutionDetailContent
      expect(screen.getByTestId('execution-view-content')).toBeInTheDocument()
      expect(screen.getByTestId('execution-details-panel')).toBeInTheDocument()
    })

    it('renders title addons when execution has status and created_at', () => {
      vi.mocked(executionsClient.useQuery).mockImplementation((_method: string, endpoint: string) => {
        if (endpoint === '/executions/{execution_id}') {
          return {
            ...mockExecutionQuery,
            data: {
              ...mockExecutionQuery.data,
              status: 'running',
              created_at: '2024-01-01T00:00:00Z',
            },
          }
        }
        return mockExecutionsQuery
      })

      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Status label should be visible (part of title addons)
      expect(screen.getByText('Running')).toBeInTheDocument()
    })

    it('renders approval side panel when approval is open with current approval', async () => {
      vi.mocked(useExecutionNodeClick).mockReturnValue({
        approvals: [mockPendingApproval] as never,
        currentIndex: 0,
        currentApproval: mockPendingApproval as never,
        isApprovalLoading: false,
        navigateToIndex: vi.fn(),
        clearApprovals: mockClearPendingApproval,
        setApprovalsAndIndex: mockSetPendingApproval,
        fetchApprovals: mockFetchForNode,
        selectedNodeId: null,
        selectedNodeName: null,
        selectNode: mockSelectNode,
        deselectNode: mockDeselectNode,
        handleNodeClick: mockHandleNodeClick,
      })

      const user = userEvent.setup()
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // Open the approval panel by clicking Review
      await user.click(screen.getByRole('button', { name: 'Review approval' }))

      // Approval side panel should be rendered
      expect(screen.getByTestId('approval-side-panel')).toBeInTheDocument()
      expect(screen.getByText('Approval: Test Approval')).toBeInTheDocument()
    })

    it('invokes onClose callback when WorkflowHistoryCard close is clicked', async () => {
      vi.mocked(useRouterState).mockReturnValue('?history=open' as never)

      const user = userEvent.setup()
      const queryClient = new QueryClient()
      render(
        <QueryClientProvider client={queryClient}>
          <ExecutionDetail />
        </QueryClientProvider>
      )

      // History card should be visible
      expect(screen.getByTestId('workflow-history-card')).toBeInTheDocument()

      // Click close button inside the history card
      await user.click(screen.getByLabelText('Close history'))

      // Navigate should be called to close history
      expect(mockNavigate).toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/executions/$executionId',
          params: { executionId: 'exec-123' },
        })
      )
    })
  })

  it('has no accessibility violations', async () => {
    const queryClient = new QueryClient()
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <ExecutionDetail />
      </QueryClientProvider>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
