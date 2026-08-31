import type { ExecutionsAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { createElement } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useExecutionWebSocket } from '../../workflows/hooks/useExecutionWebSocket'
import { useExecutionStore } from '../../workflows/stores/useExecutionStore'

import { useExecutionStreaming, useSyncActivityStore } from './useExecutionStreaming'

type Execution = ExecutionsAPI.components['schemas']['ExecutionRead']
type ActivityExecution = ExecutionsAPI.components['schemas']['ActivityExecution']

vi.mock('../../workflows/hooks/useExecutionWebSocket', () => ({
  useExecutionWebSocket: vi.fn(),
}))

vi.mock('../../workflows/stores/useExecutionStore', () => {
  const mockSetActivityExecutions = vi.fn()
  const mockInjectPendingStates = vi.fn()
  const mockActivityStates = new Map()
  return {
    useExecutionStore: Object.assign(vi.fn(), {
      getState: () => ({
        setActivityExecutions: mockSetActivityExecutions,
        injectPendingStates: mockInjectPendingStates,
        activityStates: mockActivityStates,
      }),
      __mockSet: mockSetActivityExecutions,
      __mockInject: mockInjectPendingStates,
      __mockActivityStates: mockActivityStates,
    }),
  }
})

const mockSetActivityExecutions = (useExecutionStore as unknown as { __mockSet: ReturnType<typeof vi.fn> }).__mockSet
const mockInjectPendingStates = (useExecutionStore as unknown as { __mockInject: ReturnType<typeof vi.fn> })
  .__mockInject
const mockActivityStates = (useExecutionStore as unknown as { __mockActivityStates: Map<string, unknown> })
  .__mockActivityStates

function getInjectedNodeIds(): string[] {
  return mockInjectPendingStates.mock.calls[0][0] as string[]
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

const baseExecution = {
  id: 'exec-1',
  workflow_id: 'wf-1',
  workflow_version_id: 'wfv-1',
  project_id: 'project-1',
  temporal_workflow_id: 'temporal-1',
  status: 'completed',
  created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1' },
  updated_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1' },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  completed_at: '2026-01-01T00:00:01Z',
  started_at: '2026-01-01T00:00:00Z',
  trigger_type: 'manual',
  trigger_id: 'trigger-1',
  input_data: {},
  error_details: null,
} as Execution

describe('useExecutionStreaming', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('enables WebSocket when execution is running', () => {
    const execution = { ...baseExecution, status: 'running' as const }
    renderHook(() => useExecutionStreaming('exec-1', execution), { wrapper: createWrapper() })

    expect(useExecutionWebSocket).toHaveBeenCalledWith('exec-1', expect.objectContaining({ enabled: true }))
  })

  it('enables WebSocket when execution is pending', () => {
    const execution = { ...baseExecution, status: 'pending' as const }
    renderHook(() => useExecutionStreaming('exec-1', execution), { wrapper: createWrapper() })

    expect(useExecutionWebSocket).toHaveBeenCalledWith('exec-1', expect.objectContaining({ enabled: true }))
  })

  it('enables WebSocket when execution is paused', () => {
    const execution = { ...baseExecution, status: 'paused' as const }
    renderHook(() => useExecutionStreaming('exec-1', execution), { wrapper: createWrapper() })

    expect(useExecutionWebSocket).toHaveBeenCalledWith('exec-1', expect.objectContaining({ enabled: true }))
  })

  it('disables WebSocket when execution is completed', () => {
    const execution = { ...baseExecution, status: 'completed' as const }
    renderHook(() => useExecutionStreaming('exec-1', execution), { wrapper: createWrapper() })

    expect(useExecutionWebSocket).toHaveBeenCalledWith('exec-1', expect.objectContaining({ enabled: false }))
  })

  it('disables WebSocket when executionId is undefined', () => {
    const execution = { ...baseExecution, status: 'running' as const }
    renderHook(() => useExecutionStreaming(undefined, execution), { wrapper: createWrapper() })

    expect(useExecutionWebSocket).toHaveBeenCalledWith('', expect.objectContaining({ enabled: false }))
  })

  it('passes empty string as executionId when undefined', () => {
    renderHook(() => useExecutionStreaming(undefined, undefined), { wrapper: createWrapper() })

    expect(useExecutionWebSocket).toHaveBeenCalledWith('', expect.objectContaining({ enabled: false }))
  })
})

describe('useSyncActivityStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockActivityStates.clear()
  })

  it('sets activity executions when activities are provided', () => {
    const activities: ActivityExecution[] = [
      {
        id: 'act-1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        execution_id: 'exec-1',
        activity_name: 'Task A',
        temporal_activity_id: 'ta-1',
        node_type: 'internal_activity',
        status: 'completed',
        error_details: null,
        started_at: '2026-01-01T00:00:00Z',
        completed_at: '2026-01-01T00:00:01Z',
      },
    ]

    renderHook(() => useSyncActivityStore(baseExecution, activities))

    expect(mockSetActivityExecutions).toHaveBeenCalledWith(activities)
  })

  it('clears activity executions when no activities and execution is completed', () => {
    renderHook(() => useSyncActivityStore(baseExecution, []))

    expect(mockSetActivityExecutions).toHaveBeenCalledWith([])
  })

  it('creates pending activities from workflow definition when running with no activities', () => {
    const execution = {
      ...baseExecution,
      status: 'running' as const,
      workflow_definition: {
        schema_version: '2.0.0' as const,
        name: 'test',
        triggers: [],
        edges: [],
        nodes: [
          { id: 'node-1', name: 'Task A' },
          { id: 'node-2', name: 'Task B' },
        ],
      },
    }

    renderHook(() => useSyncActivityStore(execution as unknown as Execution, []))

    const nodeIds = getInjectedNodeIds()
    expect(nodeIds).toEqual(['node-1', 'node-2'])
  })

  it('uses node id when name is missing', () => {
    const execution = {
      ...baseExecution,
      status: 'pending' as const,
      workflow_definition: {
        schema_version: '2.0.0' as const,
        name: 'test',
        triggers: [],
        edges: [],
        nodes: [{ id: 'node-no-name' }],
      },
    }

    renderHook(() => useSyncActivityStore(execution as unknown as Execution, []))

    const nodeIds = getInjectedNodeIds()
    expect(nodeIds).toEqual(['node-no-name'])
  })

  it('creates pending activities from workflow definition when paused with no activities', () => {
    const execution = {
      ...baseExecution,
      status: 'paused' as const,
      workflow_definition: {
        schema_version: '2.0.0' as const,
        name: 'test',
        triggers: [],
        edges: [],
        nodes: [
          { id: 'node-1', name: 'Approval' },
          { id: 'node-2', name: 'Wait' },
        ],
      },
    }

    renderHook(() => useSyncActivityStore(execution as unknown as Execution, []))

    const nodeIds = getInjectedNodeIds()
    expect(nodeIds).toEqual(['node-1', 'node-2'])
  })

  it('does not overwrite store when activityStates already populated (paused)', () => {
    mockActivityStates.set('node-1', { status: 'waiting' })

    const execution = {
      ...baseExecution,
      status: 'paused' as const,
      workflow_definition: {
        schema_version: '2.0.0' as const,
        name: 'test',
        triggers: [],
        edges: [],
        nodes: [{ id: 'node-1', name: 'Approval' }],
      },
    }

    renderHook(() => useSyncActivityStore(execution as unknown as Execution, []))

    expect(mockInjectPendingStates).not.toHaveBeenCalled()
  })

  it('does not overwrite store when activityStates already populated (running)', () => {
    mockActivityStates.set('node-1', { status: 'running' })

    const execution = {
      ...baseExecution,
      status: 'running' as const,
      workflow_definition: {
        schema_version: '2.0.0' as const,
        name: 'test',
        triggers: [],
        edges: [],
        nodes: [{ id: 'node-1', name: 'Task A' }],
      },
    }

    renderHook(() => useSyncActivityStore(execution as unknown as Execution, []))

    expect(mockInjectPendingStates).not.toHaveBeenCalled()
  })

  it('clears activities when execution is undefined', () => {
    renderHook(() => useSyncActivityStore(undefined, []))

    expect(mockSetActivityExecutions).toHaveBeenCalledWith([])
  })

  it('uses node ID, not display name', () => {
    const execution = {
      ...baseExecution,
      status: 'running' as const,
      workflow_definition: {
        schema_version: '2.0.0' as const,
        name: 'test',
        triggers: [],
        edges: [],
        nodes: [
          { id: 'send_email', name: 'Send Email Notification' },
          { id: 'validate', name: 'Validate Data' },
        ],
      },
    }

    renderHook(() => useSyncActivityStore(execution as unknown as Execution, []))

    const nodeIds = getInjectedNodeIds()
    expect(nodeIds).toEqual(['send_email', 'validate'])
  })

  it('includes triggers before nodes in definition order', () => {
    const execution = {
      ...baseExecution,
      status: 'running' as const,
      workflow_definition: {
        schema_version: '2.0.0' as const,
        name: 'test',
        triggers: [{ id: 'manual-trigger' }],
        edges: [],
        nodes: [
          { id: 'step-2', name: 'Second Step' },
          { id: 'step-1', name: 'First Step' },
        ],
      },
    }

    renderHook(() => useSyncActivityStore(execution as unknown as Execution, []))

    const nodeIds = getInjectedNodeIds()
    expect(nodeIds).toEqual(['manual-trigger', 'step-2', 'step-1'])
  })

  it('produces no duplicate node IDs when nodes have display names', () => {
    const execution = {
      ...baseExecution,
      status: 'running' as const,
      workflow_definition: {
        schema_version: '2.0.0' as const,
        name: 'test',
        triggers: [],
        edges: [],
        nodes: [
          { id: 'node-1', name: 'Fetch Data' },
          { id: 'node-2', name: 'Process' },
        ],
      },
    }

    renderHook(() => useSyncActivityStore(execution as unknown as Execution, []))

    const nodeIds = getInjectedNodeIds()
    expect(nodeIds).toEqual(['node-1', 'node-2'])
    expect(new Set(nodeIds).size).toBe(nodeIds.length)
  })
})
