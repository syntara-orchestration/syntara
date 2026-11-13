import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useForkWorkflow } from './useForkWorkflow'

const mockShowError = vi.fn()

vi.mock('../../../providers/alerts/AlertContext', () => ({
  useAlerts: () => ({ showError: mockShowError }),
}))

const mockMutateAsync = vi.fn()
let mockIsPending = false

vi.mock('../../../client', () => ({
  workflowClient: {
    useMutation: () => ({
      mutateAsync: mockMutateAsync,
      isPending: mockIsPending,
    }),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const MOCK_DEFINITION: Record<string, unknown> = {
  schema_version: '2.0.0',
  name: 'Test Workflow',
  nodes: [],
  edges: [],
  triggers: [],
}

describe('useForkWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockIsPending = false
  })

  it('creates a new workflow and returns its id', async () => {
    mockMutateAsync.mockResolvedValue({ id: 'new-wf-123' })

    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: MOCK_DEFINITION, workflowName: 'My Workflow', projectId: 'project-1' })
    )

    let newId: string | undefined
    await act(async () => {
      newId = await result.current.forkAsNewWorkflow()
    })

    expect(newId).toBe('new-wf-123')
    expect(mockMutateAsync).toHaveBeenCalledOnce()
    const callArgs = mockMutateAsync.mock.calls[0] as [{ body: Record<string, unknown> }]
    const body = callArgs[0].body
    expect(body.name).toContain('My Workflow - copy-')
    expect(body.description).toBe('')
    expect(body.workflow_definition).toBeDefined()
    expect(body.project_id).toBe('project-1')
  })

  it('returns undefined and shows error on API failure', async () => {
    mockMutateAsync.mockRejectedValue(new Error('Server error'))

    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: MOCK_DEFINITION, workflowName: 'My Workflow', projectId: 'project-1' })
    )

    let newId: string | undefined
    await act(async () => {
      newId = await result.current.forkAsNewWorkflow()
    })

    expect(newId).toBeUndefined()
    expect(mockShowError).toHaveBeenCalledOnce()
    expect(mockShowError).toHaveBeenCalledWith(expect.objectContaining({ title: 'Fork failed' }))
  })

  it('returns undefined when workflowDefinition is undefined', async () => {
    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: undefined, workflowName: 'My Workflow', projectId: 'project-1' })
    )

    let newId: string | undefined
    await act(async () => {
      newId = await result.current.forkAsNewWorkflow()
    })

    expect(newId).toBeUndefined()
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('returns undefined and shows error when projectId is missing', async () => {
    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: MOCK_DEFINITION, workflowName: 'My Workflow' })
    )

    let newId: string | undefined
    await act(async () => {
      newId = await result.current.forkAsNewWorkflow()
    })

    expect(newId).toBeUndefined()
    expect(mockShowError).toHaveBeenCalledOnce()
    expect(mockShowError).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Fork failed',
        description: 'Project ID is required to create a workflow',
      })
    )
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it('exposes isForkLoading from mutation isPending', () => {
    mockIsPending = true

    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: MOCK_DEFINITION, workflowName: 'Wf', projectId: 'project-1' })
    )

    expect(result.current.isForkLoading).toBe(true)
  })

  it('shows error and returns undefined on exception', async () => {
    mockMutateAsync.mockRejectedValue(new Error('Network failure'))

    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: MOCK_DEFINITION, workflowName: 'Wf', projectId: 'project-1' })
    )

    let newId: string | undefined
    await act(async () => {
      newId = await result.current.forkAsNewWorkflow()
    })

    expect(newId).toBeUndefined()
    expect(mockShowError).toHaveBeenCalledWith(expect.objectContaining({ title: 'Fork failed' }))
  })
})
