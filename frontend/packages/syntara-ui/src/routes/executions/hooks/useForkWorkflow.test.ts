import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type { NodeKind } from '../../../hooks/useNodeKindsQuery'
import {
  STEP_TYPE_PERMISSIONS_LOADING_MESSAGE,
  STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP,
} from '../../builder/stepTypePaletteGating'

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

let mockVerdicts: { nodeKindByKind: Map<string, NodeKind>; isLoading: boolean; isUnavailable: boolean }

vi.mock('../../../hooks/useNodeKindsQuery', () => ({
  useNodeKindsQuery: () => mockVerdicts,
}))

function verdict(kind: string, canWrite: boolean, label = kind): NodeKind {
  return { kind, category: 'action', can_write: canWrite, blocked_by: canWrite ? null : { kind, label } }
}

const MOCK_DEFINITION: Record<string, unknown> = {
  schema_version: '2.0.0',
  name: 'Test Workflow',
  nodes: [],
  edges: [],
  triggers: [],
}

const BLOCKED_DEFINITION: Record<string, unknown> = {
  schema_version: '2.0.0',
  name: 'Test Workflow',
  nodes: [
    { id: 'a', type: 'http' },
    { id: 'b', type: 'script' },
  ],
  edges: [
    { from: 't1', to: 'a' },
    { from: 'a', to: 'b' },
  ],
  triggers: [{ id: 't1', type: 'webhook' }],
}

function sentDefinition(): unknown {
  const callArgs = mockMutateAsync.mock.calls[0] as [{ body: Record<string, unknown> }]
  return callArgs[0].body.workflow_definition
}

describe('useForkWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockIsPending = false
    mockVerdicts = {
      nodeKindByKind: new Map([
        ['http', verdict('http', true)],
        ['script', verdict('script', false, 'Script')],
        ['webhook', verdict('webhook', false, 'Webhook')],
      ]),
      isLoading: false,
      isUnavailable: false,
    }
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
    expect(body.workflow_definition).toBe(MOCK_DEFINITION)
    expect(body.project_id).toBe('project-1')
    expect(result.current.blockedFork).toBeNull()
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

  it('asks before forking a run with blocked step types, then forks without them', async () => {
    mockMutateAsync.mockResolvedValue({ id: 'new-wf-456' })

    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: BLOCKED_DEFINITION, workflowName: 'Wf', projectId: 'project-1' })
    )

    let newId: string | undefined
    await act(async () => {
      newId = await result.current.forkAsNewWorkflow()
    })

    expect(newId).toBeUndefined()
    expect(mockMutateAsync).not.toHaveBeenCalled()
    expect(result.current.blockedFork).toEqual(
      expect.objectContaining({ labels: ['Script', 'Webhook'], losesAllTriggers: true })
    )

    await act(async () => {
      newId = await result.current.confirmBlockedFork()
    })

    expect(newId).toBe('new-wf-456')
    expect(mockMutateAsync).toHaveBeenCalledOnce()
    expect(sentDefinition()).toEqual({
      schema_version: '2.0.0',
      name: 'Test Workflow',
      nodes: [{ id: 'a', type: 'http' }],
      edges: [],
      triggers: [],
    })
    expect(result.current.blockedFork).toBeNull()
    expect(mockShowError).not.toHaveBeenCalled()
  })

  it('creates nothing when the blocked fork is cancelled', async () => {
    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: BLOCKED_DEFINITION, workflowName: 'Wf', projectId: 'project-1' })
    )

    await act(async () => {
      await result.current.forkAsNewWorkflow()
    })
    act(() => result.current.cancelBlockedFork())

    expect(result.current.blockedFork).toBeNull()
    await act(async () => {
      await result.current.confirmBlockedFork()
    })
    expect(mockMutateAsync).not.toHaveBeenCalled()
  })

  it.each([
    ['loading', { isLoading: true, isUnavailable: false }, STEP_TYPE_PERMISSIONS_LOADING_MESSAGE],
    ['unavailable', { isLoading: false, isUnavailable: true }, STEP_TYPE_PERMISSIONS_UNAVAILABLE_TOOLTIP],
  ])('refuses while the verdicts are %s', async (_state, flags, description) => {
    mockVerdicts = { ...mockVerdicts, ...flags }

    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: MOCK_DEFINITION, workflowName: 'Wf', projectId: 'project-1' })
    )

    let newId: string | undefined
    await act(async () => {
      newId = await result.current.forkAsNewWorkflow()
    })

    expect(newId).toBeUndefined()
    expect(mockMutateAsync).not.toHaveBeenCalled()
    expect(result.current.blockedFork).toBeNull()
    expect(mockShowError).toHaveBeenCalledWith({ title: 'Cannot fork workflow', description })
  })

  it('names the step types when the server still denies them', async () => {
    mockMutateAsync.mockRejectedValue({
      code: 'NODE_KIND_WRITE_DENIED',
      blocked_step_types: [{ kind: 'script', label: 'Script', reason: 'explicit_deny' }],
    })

    const { result } = renderHook(() =>
      useForkWorkflow({ workflowDefinition: MOCK_DEFINITION, workflowName: 'Wf', projectId: 'project-1' })
    )

    let newId: string | undefined
    await act(async () => {
      newId = await result.current.forkAsNewWorkflow()
    })

    expect(newId).toBeUndefined()
    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Cannot fork workflow',
      description: "You don't have permission to write these step types: Script.",
    })
  })
})
