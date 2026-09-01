import type { WorkflowAPI } from '@syntara/contracts'
import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type { BuilderAction } from '../builderReducer'
import type { EdgeConnection } from '../types/edge'
import { DEFAULT_WORKFLOW_NAME } from '../utils/workflowNaming'

import { useBuilderWorkflowLifecycle } from './useBuilderWorkflowLifecycle'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']

const processExistingWorkflowMock = vi.hoisted(() =>
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- stub ignores input; tests override via mockImplementationOnce
  vi.fn((_workflow: WorkflowWithVersion) => ({
    flattenedWorkflow: {
      schema_version: '2.0.0',
      name: 'processed',
      description: '',
      workflow: { activities: [] },
    },
    generatedEdges: [] as EdgeConnection[],
    initPayload: { name: 'processed', description: 'd' },
  }))
)

vi.mock('../utils/processExistingWorkflow', () => ({
  processExistingWorkflow: processExistingWorkflowMock,
}))

const queryOptionsMock = vi.hoisted(() => vi.fn(() => ({ queryKey: ['wf', 'list'] as const })))

vi.mock('../../../client', () => ({
  workflowClient: {
    queryOptions: queryOptionsMock,
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const refetchQueriesMock = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQueryClient: () => ({
      refetchQueries: refetchQueriesMock,
    }),
  }
})

function createDeps(overrides: Partial<Parameters<typeof useBuilderWorkflowLifecycle>[0]> = {}) {
  return {
    workflowId: 'wf-1' as string | null,
    isNew: false,
    workflow: undefined as WorkflowWithVersion | undefined,
    workflowName: 'saved-name',
    workflowsListResources: [] as { name: string }[] | undefined,
    workflowsListDataUndefined: false,
    workflowsListIsPending: false,
    workflowsListError: undefined as unknown,
    dispatch: vi.fn(),
    setWorkflow: vi.fn(),
    setStoredEdges: vi.fn(),
    loadWorkflowWithEdges: vi.fn(),
    ...overrides,
  }
}

describe('useBuilderWorkflowLifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('clears workflow and edges when workflowId changes', async () => {
    const setWorkflow = vi.fn()
    const setStoredEdges = vi.fn()
    const { rerender } = renderHook((p: ReturnType<typeof createDeps>) => useBuilderWorkflowLifecycle(p), {
      initialProps: createDeps({ workflowId: 'a', setWorkflow, setStoredEdges }),
    })
    rerender(createDeps({ workflowId: 'b', setWorkflow, setStoredEdges }))
    await waitFor(() => {
      expect(setWorkflow).toHaveBeenCalledWith(null)
      expect(setStoredEdges).toHaveBeenCalledWith([])
    })
  })

  it('initializes a new workflow when isNew', async () => {
    const loadWorkflowWithEdges = vi.fn()
    const dispatch = vi.fn()
    renderHook(() =>
      useBuilderWorkflowLifecycle(
        createDeps({
          isNew: true,
          workflowId: null,
          workflowsListResources: [],
          loadWorkflowWithEdges,
          dispatch,
        })
      )
    )
    await waitFor(() => {
      expect(loadWorkflowWithEdges).toHaveBeenCalled()
      expect(dispatch).toHaveBeenCalledWith({
        type: 'INIT_WORKFLOW',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- vitest asymmetric matcher
        payload: expect.objectContaining({ name: DEFAULT_WORKFLOW_NAME }),
      })
    })
  })

  it('does not re-init new workflow when hook re-renders with isNew', async () => {
    const loadWorkflowWithEdges = vi.fn()
    const { rerender } = renderHook((p: ReturnType<typeof createDeps>) => useBuilderWorkflowLifecycle(p), {
      initialProps: createDeps({
        isNew: true,
        workflowId: null,
        workflowsListResources: [],
        loadWorkflowWithEdges,
      }),
    })
    await waitFor(() => expect(loadWorkflowWithEdges).toHaveBeenCalledTimes(1))
    rerender(
      createDeps({
        isNew: true,
        workflowId: null,
        workflowsListResources: [{ name: 'other' }],
        loadWorkflowWithEdges,
      })
    )
    await waitFor(() => expect(loadWorkflowWithEdges).toHaveBeenCalledTimes(1))
  })

  it('loads existing workflow via processExistingWorkflow when version is present', async () => {
    const workflow = {
      id: 'wf-1',
      version: { workflow_definition: { nodes: [] } },
    } as unknown as WorkflowWithVersion
    const loadWorkflowWithEdges = vi.fn()
    const dispatch = vi.fn()
    renderHook(() =>
      useBuilderWorkflowLifecycle(
        createDeps({
          isNew: false,
          workflowId: 'wf-1',
          workflow,
          loadWorkflowWithEdges,
          dispatch,
        })
      )
    )
    await waitFor(() => {
      expect(processExistingWorkflowMock).toHaveBeenCalledWith(workflow)
      expect(loadWorkflowWithEdges).toHaveBeenCalled()
      expect(dispatch).toHaveBeenCalledWith({
        type: 'INIT_WORKFLOW',
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment -- vitest asymmetric matcher
        payload: expect.objectContaining({ name: 'processed' }),
      })
    })
  })

  it('syncs INIT_WORKFLOW from workflow metadata when editing', async () => {
    processExistingWorkflowMock.mockImplementationOnce((wf: WorkflowWithVersion) => ({
      flattenedWorkflow: {
        schema_version: '2.0.0',
        name: wf.name,
        description: wf.description ?? '',
        workflow: { activities: [] },
      },
      generatedEdges: [] as EdgeConnection[],
      initPayload: {
        name: wf.name,
        description: wf.description ?? wf.name ?? DEFAULT_WORKFLOW_NAME,
      },
    }))
    const workflow = {
      id: 'wf-1',
      name: 'Named',
      description: 'Desc',
      is_enabled: true,
      labels: { env: 'prod' },
      version: { workflow_definition: {} },
    } as unknown as WorkflowWithVersion
    const dispatch = vi.fn()
    renderHook(() =>
      useBuilderWorkflowLifecycle(
        createDeps({
          isNew: false,
          workflowId: 'wf-1',
          workflow,
          dispatch,
        })
      )
    )
    await waitFor(() => {
      expect(dispatch).toHaveBeenCalledWith({
        type: 'INIT_WORKFLOW',
        payload: {
          name: 'Named',
          description: 'Desc',
        },
      })
    })
  })

  it('dispatches SET_WORKFLOW_NAME when default name conflicts with list', async () => {
    const dispatch = vi.fn()
    renderHook(() =>
      useBuilderWorkflowLifecycle(
        createDeps({
          isNew: true,
          workflowId: null,
          workflowName: DEFAULT_WORKFLOW_NAME,
          workflowsListResources: [{ name: DEFAULT_WORKFLOW_NAME }],
          dispatch,
        })
      )
    )
    await waitFor(() => {
      expect(dispatch).toHaveBeenCalledWith({
        type: 'SET_WORKFLOW_NAME',
        payload: `${DEFAULT_WORKFLOW_NAME}-1`,
      })
    })
  })

  it('does not dispatch SET_WORKFLOW_NAME when default name is still free', async () => {
    const dispatch = vi.fn()
    renderHook(() =>
      useBuilderWorkflowLifecycle(
        createDeps({
          isNew: true,
          workflowId: null,
          workflowName: DEFAULT_WORKFLOW_NAME,
          workflowsListResources: [],
          dispatch,
        })
      )
    )
    await waitFor(() => {
      const setNameCalls = dispatch.mock.calls.filter((c) => (c[0] as BuilderAction).type === 'SET_WORKFLOW_NAME')
      expect(setNameCalls).toHaveLength(0)
    })
  })

  it('refetches workflows list once when new workflow and list was undefined', async () => {
    const { rerender } = renderHook((p: ReturnType<typeof createDeps>) => useBuilderWorkflowLifecycle(p), {
      initialProps: createDeps({
        isNew: true,
        workflowId: null,
        workflowsListDataUndefined: true,
        workflowsListIsPending: false,
        workflowsListError: undefined,
      }),
    })
    await waitFor(() => expect(refetchQueriesMock).toHaveBeenCalledTimes(1))
    rerender(
      createDeps({
        isNew: true,
        workflowId: null,
        workflowsListDataUndefined: true,
        workflowsListIsPending: false,
        workflowsListError: undefined,
      })
    )
    await waitFor(() => expect(refetchQueriesMock).toHaveBeenCalledTimes(1))
    expect(queryOptionsMock).toHaveBeenCalled()
  })

  it('does not refetch when workflows list query is pending', async () => {
    renderHook(() =>
      useBuilderWorkflowLifecycle(
        createDeps({
          isNew: true,
          workflowId: null,
          workflowsListDataUndefined: true,
          workflowsListIsPending: true,
          workflowsListError: undefined,
        })
      )
    )
    await waitFor(() => {
      expect(refetchQueriesMock).not.toHaveBeenCalled()
    })
  })

  it('does not refetch when workflows list query has an error', async () => {
    renderHook(() =>
      useBuilderWorkflowLifecycle(
        createDeps({
          isNew: true,
          workflowId: null,
          workflowsListDataUndefined: true,
          workflowsListIsPending: false,
          workflowsListError: new Error('fail'),
        })
      )
    )
    await waitFor(() => {
      expect(refetchQueriesMock).not.toHaveBeenCalled()
    })
  })
})
