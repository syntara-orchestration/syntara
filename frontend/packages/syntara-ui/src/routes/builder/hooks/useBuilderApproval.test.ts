import type { Approval } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import type { Node } from '@xyflow/react'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { approvalsClient } from '../../../client'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { EXECUTION_BADGE_DATA_ATTR } from '../components/ExecutionStatusBadge'

import { useBuilderApproval } from './useBuilderApproval'

const mockFetchForNode = vi.fn()
const mockClear = vi.fn()

const { approvalState } = vi.hoisted(() => ({
  approvalState: { pending: null as Approval | null },
}))

vi.mock('../../executions/hooks/useExecutionApproval', () => {
  const isWaitingApprovalNode = (node: { type?: string; data: Record<string, unknown> }) =>
    node.type === 'approval' && (node.data.__executionState as { status?: string } | undefined)?.status === 'waiting'

  return {
    isWaitingApprovalNode,
    useExecutionApproval: () => ({
      pendingApproval: approvalState.pending,
      isLoading: false,
      handleNodeClick: vi.fn(),
      clearPendingApproval: mockClear,
      setPendingApproval: vi.fn(),
      fetchForNode: vi.fn(),
    }),
  }
})

vi.mock('../../../client', () => ({
  approvalsClient: {
    useQuery: vi.fn(),
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function makeWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

type HookParams = Parameters<typeof useBuilderApproval>[0]

function defaultParams(overrides: Partial<HookParams> = {}): HookParams {
  return {
    mostRecentExecutionId: null,
    showMostRecentRunPanelInEditor: false,
    currentWorkflow: null,
    handleNodeClick: vi.fn(),
    isLiveRunActive: false,
    ...overrides,
  }
}

function makeNode(type: string, executionStatus?: string): Node<NodeType['data']> {
  return {
    id: 'node-1',
    type,
    position: { x: 0, y: 0 },
    data: {
      id: 'node-1',
      name: 'Test Node',
      __executionState: executionStatus ? { status: executionStatus } : undefined,
    },
  } as unknown as Node<NodeType['data']>
}

describe('useBuilderApproval', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    approvalState.pending = null
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    vi.mocked(approvalsClient.useQuery).mockReturnValue({ data: undefined, refetch: mockFetchForNode } as never)
    vi.mocked(approvalsClient.useMutation).mockReturnValue({ mutate: vi.fn(), isPending: false } as never)
  })

  it('returns approvalViewOpen as false initially', () => {
    const { result } = renderHook(() => useBuilderApproval(defaultParams()), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.approvalViewOpen).toBe(false)
    expect(result.current.pendingApproval).toBeNull()
  })

  it('opens approval view on openApprovalView call', () => {
    const { result } = renderHook(() => useBuilderApproval(defaultParams()), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => result.current.openApprovalView())
    expect(result.current.approvalViewOpen).toBe(true)
  })

  it('closes approval panel without clearing pending approval on handleApprovalClose', () => {
    const { result } = renderHook(() => useBuilderApproval(defaultParams()), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => result.current.openApprovalView())
    expect(result.current.approvalViewOpen).toBe(true)

    act(() => result.current.handleApprovalClose())
    expect(result.current.approvalViewOpen).toBe(false)
    expect(mockClear).not.toHaveBeenCalled()
  })

  it('dismisses approval view and clears pending approval on handleApprovalDismiss', () => {
    const { result } = renderHook(() => useBuilderApproval(defaultParams()), {
      wrapper: makeWrapper(queryClient),
    })

    act(() => result.current.openApprovalView())
    expect(result.current.approvalViewOpen).toBe(true)

    act(() => result.current.handleApprovalDismiss())
    expect(result.current.approvalViewOpen).toBe(false)
    expect(mockClear).toHaveBeenCalled()
  })

  it('delegates non-approval node clicks to the original handler', () => {
    const handleNodeClick = vi.fn()
    const { result } = renderHook(
      () =>
        useBuilderApproval(
          defaultParams({
            showMostRecentRunPanelInEditor: true,
            handleNodeClick,
          })
        ),
      { wrapper: makeWrapper(queryClient) }
    )

    const taskNode = makeNode('task', 'running')
    const event = new MouseEvent('click') as unknown as React.MouseEvent
    act(() => result.current.wrappedHandleNodeClick(event, taskNode))

    expect(handleNodeClick).toHaveBeenCalledWith(event, taskNode)
  })

  it('delegates all clicks to original handler when live run panel is not showing', () => {
    const handleNodeClick = vi.fn()
    const { result } = renderHook(
      () =>
        useBuilderApproval(
          defaultParams({
            showMostRecentRunPanelInEditor: false,
            handleNodeClick,
          })
        ),
      { wrapper: makeWrapper(queryClient) }
    )

    const approvalNode = makeNode('approval', 'waiting')
    const event = new MouseEvent('click') as unknown as React.MouseEvent
    act(() => result.current.wrappedHandleNodeClick(event, approvalNode))

    expect(handleNodeClick).toHaveBeenCalledWith(event, approvalNode)
  })

  it('delegates waiting approval node click to original handler when click is on node body (not badge)', () => {
    const handleNodeClick = vi.fn()
    const { result } = renderHook(
      () =>
        useBuilderApproval(
          defaultParams({
            showMostRecentRunPanelInEditor: true,
            handleNodeClick,
          })
        ),
      { wrapper: makeWrapper(queryClient) }
    )

    const approvalNode = makeNode('approval', 'waiting')
    const nodeDiv = document.createElement('div')
    const event = new MouseEvent('click', { bubbles: true }) as unknown as React.MouseEvent
    Object.defineProperty(event, 'target', { value: nodeDiv })
    act(() => result.current.wrappedHandleNodeClick(event, approvalNode))

    expect(handleNodeClick).toHaveBeenCalledWith(event, approvalNode)
  })

  it('intercepts waiting approval node click when click is on execution badge', () => {
    const handleNodeClick = vi.fn()
    const { result } = renderHook(
      () =>
        useBuilderApproval(
          defaultParams({
            showMostRecentRunPanelInEditor: true,
            handleNodeClick,
          })
        ),
      { wrapper: makeWrapper(queryClient) }
    )

    const approvalNode = makeNode('approval', 'waiting')
    const badgeDiv = document.createElement('div')
    badgeDiv.setAttribute(EXECUTION_BADGE_DATA_ATTR, '')
    document.body.appendChild(badgeDiv)
    const event = new MouseEvent('click', { bubbles: true }) as unknown as React.MouseEvent
    Object.defineProperty(event, 'target', { value: badgeDiv })
    act(() => result.current.wrappedHandleNodeClick(event, approvalNode))
    document.body.removeChild(badgeDiv)

    expect(handleNodeClick).not.toHaveBeenCalled()
  })

  it('builds activityNameMap from currentWorkflow activities', () => {
    const workflow: WorkflowDefinition = {
      schema_version: '2.0.0',
      name: 'test',
      workflow: {
        activities: [
          { id: 'a1', name: 'Step One', type: 'task', parameters: {} },
          { id: 'a2', name: 'Step Two', type: 'approval', parameters: {} },
        ],
      },
    }

    const { result } = renderHook(() => useBuilderApproval(defaultParams({ currentWorkflow: workflow })), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.activityNameMap.get('a1')).toBe('Step One')
    expect(result.current.activityNameMap.get('a2')).toBe('Step Two')
  })

  it('returns empty activityNameMap when currentWorkflow is null', () => {
    const { result } = renderHook(() => useBuilderApproval(defaultParams({ currentWorkflow: null })), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.activityNameMap.size).toBe(0)
  })

  it('returns approvalMessage from v2 parameters.prompt', () => {
    approvalState.pending = {
      id: 'approval-1',
      project_id: 'project-1',
      name: 'Approval',
      status: 'pending',
      execution_id: 'exec-1',
      approval_node_id: 'a2',
      created_at: '2026-01-01T00:00:00Z',
      next_step_approved: { id: 'step-a', name: 'Approved Step', type: 'script' },
      workflow_context: { workflow_id: 'wf-1', workflow_name: 'Test', inputs: {} },
    }

    const workflow: WorkflowDefinition = {
      schema_version: '2.0.0',
      name: 'test',
      workflow: {
        activities: [
          { id: 'a1', name: 'Step One', type: 'script', parameters: {} },
          { id: 'a2', name: 'Approval', type: 'approval', parameters: { prompt: 'Please review this change.' } },
        ],
      },
    }

    const { result } = renderHook(() => useBuilderApproval(defaultParams({ currentWorkflow: workflow })), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.approvalMessage).toBe('Please review this change.')
  })

  it('returns undefined approvalMessage when the approval node has no prompt', () => {
    approvalState.pending = {
      id: 'approval-1',
      project_id: 'project-1',
      name: 'Approval',
      status: 'pending',
      execution_id: 'exec-1',
      approval_node_id: 'a2',
      created_at: '2026-01-01T00:00:00Z',
      next_step_approved: { id: 'step-a', name: 'Approved Step', type: 'script' },
      workflow_context: { workflow_id: 'wf-1', workflow_name: 'Test', inputs: {} },
    }

    const workflow: WorkflowDefinition = {
      schema_version: '2.0.0',
      name: 'test',
      workflow: {
        activities: [{ id: 'a2', name: 'Approval', type: 'approval', parameters: {} }],
      },
    }

    const { result } = renderHook(() => useBuilderApproval(defaultParams({ currentWorkflow: workflow })), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.approvalMessage).toBeUndefined()
  })
})
