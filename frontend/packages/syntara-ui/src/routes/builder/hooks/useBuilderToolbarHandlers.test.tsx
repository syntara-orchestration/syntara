import { ActivityTypeEnum, type Activity } from '@syntara/contracts'
import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, type MockedFunction } from 'vitest'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'

import type { UseBuilderToolbarHandlersOptions } from './useBuilderToolbarHandlers'
import { useBuilderToolbarHandlers } from './useBuilderToolbarHandlers'

const mockWorkflowFetchClientGET = vi.fn()

vi.mock('../../../client', () => ({
  workflowFetchClient: { GET: (...args: unknown[]): unknown => mockWorkflowFetchClientGET(...args) },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../node-forms/useMaxWaitDuration', () => ({
  DEFAULT_MAX_WAIT_SECONDS: 2_592_000,
  fetchMaxWaitDuration: () => Promise.resolve(2_592_000),
}))

vi.mock('../../../stores/useWorkflowStore', () => ({
  useWorkflowStore: {
    getState: vi.fn(),
    temporal: { getState: vi.fn(() => ({ clear: vi.fn() })) },
  },
}))

type ExecuteWorkflow = UseBuilderToolbarHandlersOptions['executeWorkflow']
type DeleteWorkflow = UseBuilderToolbarHandlersOptions['deleteWorkflow']
type ReactFlowInstanceParam = UseBuilderToolbarHandlersOptions['reactFlowInstance']

/** Minimal `@xyflow/react` instance for tests — full type is large; only `setNodes` is used by the hook. */
function createMockReactFlowInstance(overrides: { setNodes?: ReturnType<typeof vi.fn> } = {}): ReactFlowInstanceParam {
  return {
    setNodes: overrides.setNodes ?? vi.fn(),
  } as unknown as ReactFlowInstanceParam
}

function minimalWorkflow(overrides: Partial<WorkflowDefinition> = {}): WorkflowDefinition {
  return {
    schema_version: '2.0.0',
    name: 'test-wf',
    description: 'd',
    workflow: {
      activities: [
        { type: 'script', id: 'task-1', name: 'Task 1', parameters: { language: 'python', code: 'print("hello")' } },
      ] as Activity[],
    },
    triggers: [{ type: 'manual', id: 'trigger-1', parameters: {} }],
    ...overrides,
  }
}

function buildOptions(overrides: Partial<UseBuilderToolbarHandlersOptions> = {}): UseBuilderToolbarHandlersOptions {
  return {
    workflow: { id: 'wf-1' },
    workflowName: 'My workflow',
    detailsOpen: false,
    historyCardOpen: false,
    reactFlowInstance: createMockReactFlowInstance(),
    executionsQuery: { refetch: vi.fn().mockResolvedValue({}) },
    dispatch: vi.fn(),
    executeWorkflow: vi.fn(),
    deleteWorkflow: vi.fn(),
    showSuccess: vi.fn(),
    showError: vi.fn(),
    setLocation: vi.fn(),
    handleSaveWorkflow: vi.fn().mockResolvedValue(true),
    currentWorkflow: minimalWorkflow(),
    loadedVersion: null,
    ...overrides,
  }
}

describe('useBuilderToolbarHandlers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default to clean state with edges for validation
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: false,
      edges: [
        {
          id: 'trigger-1-task-1',
          source: 'trigger-1',
          target: 'task-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ],
    } as ReturnType<typeof useWorkflowStore.getState>)
  })

  it('handleRunWorkflow does not call executeWorkflow when workflow is missing', async () => {
    const executeWorkflow = vi.fn() as MockedFunction<ExecuteWorkflow>
    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ workflow: undefined, executeWorkflow }))
    )

    await result.current.handleRunWorkflow()

    expect(executeWorkflow).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow saves workflow but shows error when workflow has no triggers', async () => {
    const executeWorkflow = vi.fn()
    const showError = vi.fn()
    const dispatch = vi.fn()
    const handleSaveWorkflow = vi.fn().mockResolvedValue(true)
    const currentWorkflow = minimalWorkflow({ triggers: undefined })

    // Mock dirty state so save is called
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: true,
      edges: [
        {
          id: 'trigger-1-task-1',
          source: 'trigger-1',
          target: 'task-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(
        buildOptions({ executeWorkflow, showError, dispatch, currentWorkflow, handleSaveWorkflow })
      )
    )

    await result.current.handleRunWorkflow()

    // Save should be called first
    expect(handleSaveWorkflow).toHaveBeenCalled()
    // Then validation error shown
    expect(showError).toHaveBeenCalledWith({
      title: 'Cannot run workflow',
      description: expect.stringContaining('at least one trigger') as unknown as string,
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
    // But execution should not happen
    expect(executeWorkflow).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow saves workflow but shows error when workflow has no activities', async () => {
    const executeWorkflow = vi.fn()
    const showError = vi.fn()
    const dispatch = vi.fn()
    const handleSaveWorkflow = vi.fn().mockResolvedValue(true)
    const currentWorkflow = minimalWorkflow({ workflow: { activities: [] } })

    // Mock dirty state so save is called
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: true,
      edges: [
        {
          id: 'trigger-1-task-1',
          source: 'trigger-1',
          target: 'task-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(
        buildOptions({ executeWorkflow, showError, dispatch, currentWorkflow, handleSaveWorkflow })
      )
    )

    await result.current.handleRunWorkflow()

    // Save should be called first
    expect(handleSaveWorkflow).toHaveBeenCalled()
    // Then validation error shown
    expect(showError).toHaveBeenCalledWith({
      title: 'Cannot run workflow',
      description: expect.stringContaining('at least one step') as unknown as string,
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
    // But execution should not happen
    expect(executeWorkflow).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow saves workflow but shows error when workflow has no connections', async () => {
    const executeWorkflow = vi.fn()
    const showError = vi.fn()
    const dispatch = vi.fn()
    const handleSaveWorkflow = vi.fn().mockResolvedValue(true)

    // Mock dirty state with no edges
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: true,
      edges: [],
    } as unknown as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ executeWorkflow, showError, dispatch, handleSaveWorkflow }))
    )

    await result.current.handleRunWorkflow()

    // Save should be called first
    expect(handleSaveWorkflow).toHaveBeenCalled()
    // Then validation error shown
    expect(showError).toHaveBeenCalledWith({
      title: 'Cannot run workflow',
      description: expect.stringContaining('at least one connection') as unknown as string,
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
    // But execution should not happen
    expect(executeWorkflow).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow invokes executeWorkflow and navigates to execution on success', async () => {
    const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
      const options = args[1]
      options?.onSuccess?.({ id: 'exec-99' })
    }) as MockedFunction<ExecuteWorkflow>
    const setLocation = vi.fn()
    const dispatch = vi.fn()
    const showSuccess = vi.fn()
    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ executeWorkflow, setLocation, dispatch, showSuccess }))
    )

    await result.current.handleRunWorkflow(undefined, 'trigger-1')

    expect(executeWorkflow).toHaveBeenCalledTimes(1)
    const [variables, options] = executeWorkflow.mock.calls[0]
    expect(variables).toEqual({ body: { workflow_id: 'wf-1', input_data: {}, trigger_node_id: 'trigger-1' } })
    expect(options?.onSuccess).toEqual(expect.any(Function))
    expect(options?.onError).toEqual(expect.any(Function))
    expect(showSuccess).not.toHaveBeenCalled()
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
    expect(setLocation).toHaveBeenCalledWith('/executions/exec-99?history=closed')
  })

  it('handleRunWorkflow shows error on failure', async () => {
    const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
      const options = args[1]
      options?.onError?.(new Error('boom'))
    }) as MockedFunction<ExecuteWorkflow>
    const showError = vi.fn()
    const { result } = renderHook(() => useBuilderToolbarHandlers(buildOptions({ executeWorkflow, showError })))

    await result.current.handleRunWorkflow()

    expect(showError).toHaveBeenCalledWith({
      title: 'Failed to run workflow',
      description: 'Failed to start workflow "My workflow": boom',
    })
  })

  it('handleRunWorkflow passes blockOnWarnings: true to handleSaveWorkflow', async () => {
    const handleSaveWorkflow = vi.fn().mockResolvedValue(true)
    const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
      args[1]?.onSuccess?.({ id: 'exec-1' })
    }) as MockedFunction<ExecuteWorkflow>
    const dispatch = vi.fn()

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ handleSaveWorkflow, executeWorkflow, dispatch }))
    )

    await result.current.handleRunWorkflow()

    expect(handleSaveWorkflow).toHaveBeenCalledWith({ blockOnWarnings: true })
  })

  it('handleRunWorkflow saves workflow first when isDirty', async () => {
    const handleSaveWorkflow = vi.fn().mockResolvedValue(true)
    const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
      args[1]?.onSuccess?.({ id: 'exec-1' })
    }) as MockedFunction<ExecuteWorkflow>
    const dispatch = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: true,
      edges: [
        {
          id: 'trigger-1-task-1',
          source: 'trigger-1',
          target: 'task-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ handleSaveWorkflow, executeWorkflow, dispatch }))
    )

    await result.current.handleRunWorkflow()

    expect(handleSaveWorkflow).toHaveBeenCalledTimes(1)
    expect(executeWorkflow).toHaveBeenCalledTimes(1)
    expect(handleSaveWorkflow.mock.invocationCallOrder[0]).toBeLessThan(executeWorkflow.mock.invocationCallOrder[0])
  })

  it('handleRunWorkflow does not execute when save fails and isDirty', async () => {
    const handleSaveWorkflow = vi.fn().mockResolvedValue(false)
    const executeWorkflow = vi.fn()
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: true,
      edges: [
        {
          id: 'trigger-1-task-1',
          source: 'trigger-1',
          target: 'task-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ handleSaveWorkflow, executeWorkflow }))
    )

    await result.current.handleRunWorkflow()

    expect(handleSaveWorkflow).toHaveBeenCalledTimes(1)
    expect(executeWorkflow).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow always saves before executing (even when not isDirty)', async () => {
    const handleSaveWorkflow = vi.fn().mockResolvedValue(true)
    const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
      args[1]?.onSuccess?.({ id: 'exec-99' })
    }) as MockedFunction<ExecuteWorkflow>

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ handleSaveWorkflow, executeWorkflow }))
    )

    await result.current.handleRunWorkflow()

    expect(handleSaveWorkflow).toHaveBeenCalledTimes(1)
    expect(executeWorkflow).toHaveBeenCalledTimes(1)
  })

  it('handleDeleteWorkflow does not call deleteWorkflow when workflow is missing', () => {
    const deleteWorkflow = vi.fn() as MockedFunction<DeleteWorkflow>
    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ workflow: undefined, deleteWorkflow }))
    )

    result.current.handleDeleteWorkflow()

    expect(deleteWorkflow).not.toHaveBeenCalled()
  })

  it('handleDeleteWorkflow invokes deleteWorkflow on success', () => {
    const deleteWorkflow = vi.fn((...args: Parameters<DeleteWorkflow>) => {
      const options = args[1]
      options?.onSuccess?.()
    }) as MockedFunction<DeleteWorkflow>
    const setLocation = vi.fn()
    const showSuccess = vi.fn()
    const dispatch = vi.fn()
    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ deleteWorkflow, setLocation, showSuccess, dispatch }))
    )

    result.current.handleDeleteWorkflow()

    expect(deleteWorkflow).toHaveBeenCalledTimes(1)
    const [variables, options] = deleteWorkflow.mock.calls[0]
    expect(variables).toEqual({ params: { path: { workflow_id: 'wf-1' } } })
    expect(options?.onSuccess).toEqual(expect.any(Function))
    expect(options?.onError).toEqual(expect.any(Function))
    expect(showSuccess).toHaveBeenCalledWith({
      title: 'Workflow deleted',
      description: 'Workflow "My workflow" has been deleted.',
    })
    expect(setLocation).toHaveBeenCalledWith('/workflows')
  })

  it('handleToggleDetails dispatches and clears node selection when opening', () => {
    const setNodes = vi.fn()
    const dispatch = vi.fn()
    const reactFlowInstance = createMockReactFlowInstance({ setNodes })
    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ detailsOpen: false, dispatch, reactFlowInstance }))
    )

    result.current.handleToggleDetails()

    expect(dispatch).toHaveBeenCalledWith({ type: 'TOGGLE_DETAILS' })
    expect(setNodes).toHaveBeenCalled()
  })

  it('handleToggleDetails only dispatches when panel already open', () => {
    const setNodes = vi.fn()
    const reactFlowInstance = createMockReactFlowInstance({ setNodes })
    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ detailsOpen: true, reactFlowInstance }))
    )

    result.current.handleToggleDetails()

    expect(setNodes).not.toHaveBeenCalled()
  })

  it('handleToggleHistory refetches when opening history', () => {
    const refetch = vi.fn().mockResolvedValue({})
    const dispatch = vi.fn()
    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ historyCardOpen: false, executionsQuery: { refetch }, dispatch }))
    )

    result.current.handleToggleHistory()

    expect(dispatch).toHaveBeenCalledWith({ type: 'TOGGLE_HISTORY' })
    expect(refetch).toHaveBeenCalled()
  })

  it('handleToggleHistory does not refetch when history already open', () => {
    const refetch = vi.fn()
    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ historyCardOpen: true, executionsQuery: { refetch } }))
    )

    result.current.handleToggleHistory()

    expect(refetch).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow dispatches SET_CONFIRM_DIALOG:false when save throws', async () => {
    const handleSaveWorkflow = vi.fn().mockRejectedValue(new Error('network'))
    const executeWorkflow = vi.fn() as MockedFunction<ExecuteWorkflow>
    const dispatch = vi.fn()

    // Mock isDirty state with edges for validation
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: true,
      edges: [
        {
          id: 'trigger-1-task-1',
          source: 'trigger-1',
          target: 'task-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ handleSaveWorkflow, executeWorkflow, dispatch }))
    )
    await result.current.handleRunWorkflow()

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
    expect(executeWorkflow).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow saves and executes when isDirty', async () => {
    const handleSaveWorkflow = vi.fn().mockResolvedValue(true)
    const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
      args[1]?.onSuccess?.({ id: 'exec-1' })
    }) as MockedFunction<ExecuteWorkflow>

    // Mock isDirty state with edges for validation
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: true,
      edges: [
        {
          id: 'trigger-1-task-1',
          source: 'trigger-1',
          target: 'task-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ handleSaveWorkflow, executeWorkflow }))
    )

    await result.current.handleRunWorkflow()

    // Verify save was called before execute
    expect(handleSaveWorkflow).toHaveBeenCalledTimes(1)
    expect(executeWorkflow).toHaveBeenCalledTimes(1)

    // Verify order: handleSaveWorkflow should be called before executeWorkflow
    const saveCallOrder = handleSaveWorkflow.mock.invocationCallOrder[0]
    const executeCallOrder = executeWorkflow.mock.invocationCallOrder[0]
    expect(saveCallOrder).toBeLessThan(executeCallOrder)
  })

  it('handleRunWorkflow handles onSuccess without data.id', async () => {
    const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
      args[1]?.onSuccess?.({})
    }) as MockedFunction<ExecuteWorkflow>
    const dispatch = vi.fn()

    // Clean state already set in beforeEach with edges
    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: false,
      edges: [
        {
          id: 'trigger-1-task-1',
          source: 'trigger-1',
          target: 'task-1',
          sourceHandle: 'source',
          targetHandle: 'target',
        },
      ],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() => useBuilderToolbarHandlers(buildOptions({ executeWorkflow, dispatch })))

    await result.current.handleRunWorkflow()

    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
    expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_MOST_RECENT_EXECUTION' }))
  })

  it('handleRunWorkflow passes triggerNodeId in the execution body', async () => {
    const executeWorkflow = vi.fn() as MockedFunction<ExecuteWorkflow>

    const { result } = renderHook(() => useBuilderToolbarHandlers(buildOptions({ executeWorkflow })))
    await result.current.handleRunWorkflow({ key: 'val' }, 'trigger-node-1')

    const [variables] = executeWorkflow.mock.calls[0]
    expect(variables.body.trigger_node_id).toBe('trigger-node-1')
    expect(variables.body.input_data).toEqual({ key: 'val' })
  })

  it('handleRunWorkflow always sends trigger_node_id in body', async () => {
    const executeWorkflow = vi.fn() as MockedFunction<ExecuteWorkflow>

    const { result } = renderHook(() => useBuilderToolbarHandlers(buildOptions({ executeWorkflow })))
    await result.current.handleRunWorkflow()

    const [variables] = executeWorkflow.mock.calls[0]
    expect(variables.body).toHaveProperty('trigger_node_id')
    expect(variables.body.input_data).toEqual({})
  })

  it('handleRunWorkflow shows error when currentWorkflow is null', async () => {
    const executeWorkflow = vi.fn() as MockedFunction<ExecuteWorkflow>
    const showError = vi.fn()
    const dispatch = vi.fn()

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ executeWorkflow, showError, dispatch, currentWorkflow: null }))
    )

    await result.current.handleRunWorkflow()

    expect(showError).toHaveBeenCalledWith({
      title: 'Cannot run workflow',
      description: 'No workflow data available',
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
    expect(executeWorkflow).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow handles wait node with no name (falls back to Untitled)', async () => {
    const executeWorkflow = vi.fn() as MockedFunction<ExecuteWorkflow>
    const showError = vi.fn()
    const dispatch = vi.fn()
    const currentWorkflow = minimalWorkflow({
      workflow: {
        activities: [
          { type: ActivityTypeEnum.WAIT, id: 'wait-1', name: '', parameters: { duration: 99_999_999 } },
        ] as Activity[],
      },
      triggers: [{ type: 'manual', id: 'trigger-1', parameters: {} }],
    })

    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: false,
      edges: [{ id: 'e1', source: 'trigger-1', target: 'wait-1', sourceHandle: 'source', targetHandle: 'target' }],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ executeWorkflow, showError, dispatch, currentWorkflow }))
    )

    await result.current.handleRunWorkflow()

    expect(showError).toHaveBeenCalledWith({
      title: 'Cannot run workflow',
      description: expect.stringContaining('Untitled') as unknown as string,
    })
    expect(executeWorkflow).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow shows error when wait node exceeds max duration', async () => {
    const executeWorkflow = vi.fn() as MockedFunction<ExecuteWorkflow>
    const showError = vi.fn()
    const dispatch = vi.fn()
    const currentWorkflow = minimalWorkflow({
      workflow: {
        activities: [
          {
            type: ActivityTypeEnum.WAIT,
            id: 'wait-1',
            name: 'Long Wait',
            parameters: { duration: 99_999_999 },
          },
        ] as Activity[],
      },
      triggers: [{ type: 'manual', id: 'trigger-1', parameters: {} }],
    })

    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: false,
      edges: [{ id: 'e1', source: 'trigger-1', target: 'wait-1', sourceHandle: 'source', targetHandle: 'target' }],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ executeWorkflow, showError, dispatch, currentWorkflow }))
    )

    await result.current.handleRunWorkflow()

    expect(showError).toHaveBeenCalledWith({
      title: 'Cannot run workflow',
      description: expect.stringContaining('exceeds maximum allowed') as unknown as string,
    })
    expect(executeWorkflow).not.toHaveBeenCalled()
  })

  it('handleRunWorkflow passes validation when wait node is within max duration', async () => {
    const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
      args[1]?.onSuccess?.({ id: 'exec-1' })
    }) as MockedFunction<ExecuteWorkflow>
    const currentWorkflow = minimalWorkflow({
      workflow: {
        activities: [
          { type: ActivityTypeEnum.WAIT, id: 'wait-1', name: 'Short Wait', parameters: { duration: 300 } },
        ] as Activity[],
      },
      triggers: [{ type: 'manual', id: 'trigger-1', parameters: {} }],
    })

    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: false,
      edges: [{ id: 'e1', source: 'trigger-1', target: 'wait-1', sourceHandle: 'source', targetHandle: 'target' }],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() => useBuilderToolbarHandlers(buildOptions({ executeWorkflow, currentWorkflow })))

    await result.current.handleRunWorkflow()

    expect(executeWorkflow).toHaveBeenCalled()
  })

  it('handleRunWorkflow handles wait node with missing config gracefully', async () => {
    const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
      args[1]?.onSuccess?.({ id: 'exec-1' })
    }) as MockedFunction<ExecuteWorkflow>
    const currentWorkflow = minimalWorkflow({
      workflow: {
        activities: [{ type: ActivityTypeEnum.WAIT, id: 'wait-1', name: 'No Config', parameters: {} }] as Activity[],
      },
      triggers: [{ type: 'manual', id: 'trigger-1', parameters: {} }],
    })

    vi.mocked(useWorkflowStore.getState).mockReturnValue({
      isDirty: false,
      edges: [{ id: 'e1', source: 'trigger-1', target: 'wait-1', sourceHandle: 'source', targetHandle: 'target' }],
    } as ReturnType<typeof useWorkflowStore.getState>)

    const { result } = renderHook(() => useBuilderToolbarHandlers(buildOptions({ executeWorkflow, currentWorkflow })))

    await result.current.handleRunWorkflow()

    expect(executeWorkflow).toHaveBeenCalled()
  })

  describe('pre-flight version conflict check', () => {
    it('calls onRunConflict when server has a newer version', async () => {
      const onRunConflict = vi.fn()
      const executeWorkflow = vi.fn() as MockedFunction<ExecuteWorkflow>
      const dispatch = vi.fn()

      mockWorkflowFetchClientGET.mockResolvedValue({
        data: { current_version: 5, updated_at: '2026-06-25T12:00:00Z' },
      })

      const { result } = renderHook(() =>
        useBuilderToolbarHandlers(buildOptions({ executeWorkflow, dispatch, loadedVersion: 3, onRunConflict }))
      )

      await result.current.handleRunWorkflow()

      expect(onRunConflict).toHaveBeenCalledWith(expect.objectContaining({ currentVersion: 5, expectedVersion: 3 }))
      expect(dispatch).toHaveBeenCalledWith({ type: 'SET_CONFIRM_DIALOG', payload: false })
      expect(executeWorkflow).not.toHaveBeenCalled()
    })

    it('proceeds with run when server version matches loaded version', async () => {
      const onRunConflict = vi.fn()
      const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
        args[1]?.onSuccess?.({ id: 'exec-1' })
      }) as MockedFunction<ExecuteWorkflow>

      mockWorkflowFetchClientGET.mockResolvedValue({
        data: { current_version: 3, updated_at: '2026-06-25T12:00:00Z' },
      })

      const { result } = renderHook(() =>
        useBuilderToolbarHandlers(buildOptions({ executeWorkflow, loadedVersion: 3, onRunConflict }))
      )

      await result.current.handleRunWorkflow()

      expect(onRunConflict).not.toHaveBeenCalled()
      expect(executeWorkflow).toHaveBeenCalled()
    })

    it('skips pre-flight check when skipPreflightCheck is true', async () => {
      const onRunConflict = vi.fn()
      const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
        args[1]?.onSuccess?.({ id: 'exec-1' })
      }) as MockedFunction<ExecuteWorkflow>

      const { result } = renderHook(() =>
        useBuilderToolbarHandlers(buildOptions({ executeWorkflow, loadedVersion: 3, onRunConflict }))
      )

      await result.current.handleRunWorkflow(undefined, undefined, { skipPreflightCheck: true })

      expect(mockWorkflowFetchClientGET).not.toHaveBeenCalled()
      expect(onRunConflict).not.toHaveBeenCalled()
      expect(executeWorkflow).toHaveBeenCalled()
    })

    it('skips pre-flight check when loadedVersion is null', async () => {
      const onRunConflict = vi.fn()
      const executeWorkflow = vi.fn((...args: Parameters<ExecuteWorkflow>) => {
        args[1]?.onSuccess?.({ id: 'exec-1' })
      }) as MockedFunction<ExecuteWorkflow>

      const { result } = renderHook(() =>
        useBuilderToolbarHandlers(buildOptions({ executeWorkflow, loadedVersion: null, onRunConflict }))
      )

      await result.current.handleRunWorkflow()

      expect(mockWorkflowFetchClientGET).not.toHaveBeenCalled()
      expect(executeWorkflow).toHaveBeenCalled()
    })
  })

  it('handleDeleteWorkflow shows error and dispatches SET_DELETE_DIALOG on failure', () => {
    const deleteWorkflow = vi.fn((...args: Parameters<DeleteWorkflow>) => {
      args[1]?.onError?.(new Error('delete failed'))
    }) as MockedFunction<DeleteWorkflow>
    const showError = vi.fn()
    const dispatch = vi.fn()
    const { result } = renderHook(() =>
      useBuilderToolbarHandlers(buildOptions({ deleteWorkflow, showError, dispatch }))
    )

    result.current.handleDeleteWorkflow()

    expect(showError).toHaveBeenCalledWith({
      title: 'Failed to delete workflow',
      description: 'Failed to delete workflow "My workflow": delete failed',
    })
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_DELETE_DIALOG', payload: false })
  })
})
