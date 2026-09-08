import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import {
  useWorkflowVerification,
  extractValidationErrors,
  extractValidationErrorsFromUnknown,
} from './useWorkflowVerification'

const mockShowError = vi.fn()
const mockShowSuccess = vi.fn()
const mockDispatch = vi.fn()
const mockPost = vi.fn()
const mockBuildDefinition = vi.fn<(...args: unknown[]) => Record<string, unknown>>()
const mockGetState = vi.fn<() => Record<string, unknown>>()
const mockSetValidationErrorCount = vi.fn()

vi.mock('../../client', () => ({
  workflowFetchClient: { POST: (...args: unknown[]) => mockPost(...args) as Promise<unknown> },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../providers/alerts', () => ({
  useAlerts: () => ({ showError: mockShowError, showSuccess: mockShowSuccess }),
}))

vi.mock('../../stores/useWorkflowStore', () => {
  const store = (selector: (state: Record<string, unknown>) => unknown) => selector({ validationErrorCount: 0 })
  store.getState = () => ({ ...mockGetState(), setValidationErrorCount: mockSetValidationErrorCount })
  return { useWorkflowStore: store }
})

vi.mock('../../utils/apiErrors', () => ({
  getErrorMessage: (err: unknown) => (err instanceof Error ? err.message : 'Unknown error'),
}))

const mockValidateWorkflow = vi.fn<() => { errors: Array<{ message: string; nodeId?: string; severity?: string }> }>()
const mockValidateMinimum = vi.fn<() => Array<{ message: string; nodeId?: string; severity?: string }>>()

vi.mock('./utils/validation', () => ({
  validateWorkflow: () => mockValidateWorkflow(),
}))

vi.mock('./utils/validation/rules/validateMinimumWorkflow', () => ({
  validateMinimumWorkflow: () => mockValidateMinimum(),
}))

vi.mock('./utils/workflowDefinitionBuilder', () => ({
  buildWorkflowDefinition: (...args: unknown[]) => mockBuildDefinition(...args),
}))

beforeEach(() => {
  vi.clearAllMocks()
  mockGetState.mockReturnValue({
    currentWorkflow: null,
    edges: [],
  })
  mockValidateWorkflow.mockReturnValue({ errors: [] })
  mockValidateMinimum.mockReturnValue([])
})

describe('useWorkflowVerification', () => {
  function renderVerificationHook() {
    return renderHook(() => useWorkflowVerification({ dispatch: mockDispatch }))
  }

  const workflowState = {
    currentWorkflow: {
      name: 'Test',
      description: 'desc',
      workflow: {
        activities: [
          { type: 'script', id: 'n1', name: 'Step 1', parameters: { language: 'python', code: 'print(1)' } },
        ],
      },
      triggers: [{ type: 'manual_trigger', id: 't1' }],
    },
    edges: [{ id: 'e1', source: 't1', target: 'n1', sourceHandle: 'source', targetHandle: 'target' }],
    nodePositions: {},
    _positionsUserModified: false,
  }

  it('closes kebab when no current workflow', () => {
    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    expect(mockDispatch).toHaveBeenCalledWith({ type: 'SET_KEBAB_OPEN', payload: false })
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('clears stale validation errors before starting verification', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: { is_valid: true, findings: [] },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    const clearCall = mockDispatch.mock.calls.find(
      (call) => (call[0] as { type: string }).type === 'CLEAR_VALIDATION_ERRORS'
    )
    expect(clearCall).toBeDefined()

    await waitFor(() => {
      expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Workflow verified' })
    })
  })

  it('clears validation errors and shows success alert when workflow is valid', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: { is_valid: true, findings: [] },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalledWith({ type: 'CLEAR_VALIDATION_ERRORS' })
      expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Workflow verified' })
    })
  })

  it('dispatches validation errors when workflow is invalid via 200', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: {
        is_valid: false,
        findings: [
          { message: 'Node A is disconnected', node_id: 'node-1' },
          { message: 'Missing condition branch', node_id: null },
        ],
      },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalledWith({
        type: 'SET_VALIDATION_ERRORS',
        payload: [
          { message: 'Node A is disconnected', nodeId: 'node-1', severity: 'error', fieldPath: null },
          { message: 'Missing condition branch', nodeId: null, severity: 'error', fieldPath: null },
        ],
      })
      expect(mockShowError).not.toHaveBeenCalled()
    })
  })

  it('dispatches validation errors from 400 response with validation_result', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: undefined,
      error: {
        type: 'https://api.example.com/errors/validation-error',
        title: 'Workflow Definition Invalid',
        detail: 'The workflow definition failed validation',
        code: 'WORKFLOW_DEFINITION_INVALID',
        retryable: false,
        validation_result: {
          findings: [
            { message: 'Workflow must have at least one trigger', node_id: null },
            { message: 'Node config invalid', node_id: 'node-2' },
          ],
        },
      },
      response: { ok: false },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalledWith({
        type: 'SET_VALIDATION_ERRORS',
        payload: [
          { message: 'Workflow must have at least one trigger', nodeId: null, severity: 'error', fieldPath: null },
          { message: 'Node config invalid', nodeId: 'node-2', severity: 'error', fieldPath: null },
        ],
      })
    })
  })

  it('shows error toast when 400 response has no validation_result', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: undefined,
      error: {
        title: 'Server Error',
        detail: 'Internal server error',
      },
      response: { ok: false },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Verification failed',
        description: 'Unknown error',
      })
    })
  })

  it('shows error when build definition throws', () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockImplementation(() => {
      throw new Error('Name is required')
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    expect(mockShowError).toHaveBeenCalledWith({
      title: 'Verification failed',
      description: 'Name is required',
    })
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('shows error when fetch rejects', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockRejectedValue(new Error('Network error'))

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Verification failed',
        description: 'Network error',
      })
    })
  })

  it('uses fallback defaults when workflow has no triggers, name, or description', async () => {
    mockGetState.mockReturnValue({
      currentWorkflow: {
        workflow: { activities: [] },
      },
      edges: [],
      nodePositions: {},
      _positionsUserModified: false,
    })
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: { is_valid: true, findings: [] },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockBuildDefinition).toHaveBeenCalledWith('workflow', '', [], [], {
        edges: [],
        nodePositions: {},
      })
    })
  })

  it('passes nodePositions when _positionsUserModified is true', async () => {
    const positions = { 'node-1': { x: 100, y: 200 } }
    mockGetState.mockReturnValue({
      ...workflowState,
      nodePositions: positions,
      _positionsUserModified: true,
    })
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: { is_valid: true, findings: [] },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockBuildDefinition).toHaveBeenCalledWith(
        'Test',
        'desc',
        workflowState.currentWorkflow.workflow.activities,
        workflowState.currentWorkflow.triggers,
        {
          edges: workflowState.edges,
          nodePositions: positions,
        }
      )
    })
  })

  it('includes nodeName in dispatched errors when activity matches store', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: {
        is_valid: false,
        findings: [
          { message: 'Node is disconnected', node_id: 'n1' },
          { message: 'Missing trigger', node_id: null },
        ],
      },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalledWith({
        type: 'SET_VALIDATION_ERRORS',
        payload: [
          { message: 'Node is disconnected', nodeId: 'n1', nodeName: 'Step 1', severity: 'error', fieldPath: null },
          { message: 'Missing trigger', nodeId: null, severity: 'error', fieldPath: null },
        ],
      })
    })
  })

  describe('onValid callback', () => {
    it('calls onValid callback when workflow is valid', async () => {
      mockGetState.mockReturnValue(workflowState)
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
      mockPost.mockResolvedValue({
        data: { is_valid: true, findings: [] },
        error: undefined,
        response: { ok: true },
      })

      const onValid = vi.fn()
      const { result } = renderVerificationHook()

      act(() => result.current.handleVerify(onValid))

      await waitFor(() => {
        expect(onValid).toHaveBeenCalledTimes(1)
        expect(mockShowSuccess).not.toHaveBeenCalled()
      })
    })

    it('shows success toast when no onValid callback provided', async () => {
      mockGetState.mockReturnValue(workflowState)
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
      mockPost.mockResolvedValue({
        data: { is_valid: true, findings: [] },
        error: undefined,
        response: { ok: true },
      })

      const { result } = renderVerificationHook()

      act(() => result.current.handleVerify())

      await waitFor(() => {
        expect(mockShowSuccess).toHaveBeenCalledWith({ title: 'Workflow verified' })
      })
    })

    it('does not call onValid when workflow is invalid', async () => {
      mockGetState.mockReturnValue(workflowState)
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
      mockPost.mockResolvedValue({
        data: {
          is_valid: false,
          findings: [{ message: 'Error', node_id: null }],
        },
        error: undefined,
        response: { ok: true },
      })

      const onValid = vi.fn()
      const { result } = renderVerificationHook()

      act(() => result.current.handleVerify(onValid))

      await waitFor(() => {
        expect(onValid).not.toHaveBeenCalled()
      })
    })
  })

  describe('validationErrorCount store updates', () => {
    it('sets validationErrorCount to 0 on valid response', async () => {
      mockGetState.mockReturnValue(workflowState)
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
      mockPost.mockResolvedValue({
        data: { is_valid: true, findings: [] },
        error: undefined,
        response: { ok: true },
      })

      const { result } = renderVerificationHook()

      act(() => result.current.handleVerify())

      await waitFor(() => {
        expect(mockSetValidationErrorCount).toHaveBeenCalledWith(0)
      })
    })

    it('sets validationErrorCount on invalid response', async () => {
      mockGetState.mockReturnValue(workflowState)
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
      mockPost.mockResolvedValue({
        data: {
          is_valid: false,
          findings: [{ message: 'Error', node_id: null }],
        },
        error: undefined,
        response: { ok: true },
      })

      const { result } = renderVerificationHook()

      act(() => result.current.handleVerify())

      await waitFor(() => {
        expect(mockSetValidationErrorCount).toHaveBeenCalledWith(1)
      })
    })

    it('sets validationErrorCount on error with validation_result', async () => {
      mockGetState.mockReturnValue(workflowState)
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
      mockPost.mockResolvedValue({
        data: undefined,
        error: {
          validation_result: {
            findings: [{ message: 'Error', node_id: null }],
          },
        },
        response: { ok: false },
      })

      const { result } = renderVerificationHook()

      act(() => result.current.handleVerify())

      await waitFor(() => {
        expect(mockSetValidationErrorCount).toHaveBeenCalledWith(1)
      })
    })

    it('shows error and returns early on error without validation_result', async () => {
      mockGetState.mockReturnValue(workflowState)
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
      mockPost.mockResolvedValue({
        data: undefined,
        error: {
          title: 'Server Error',
          detail: 'Internal server error',
        },
        response: { ok: false },
      })

      const { result } = renderVerificationHook()

      act(() => result.current.handleVerify())

      await waitFor(() => {
        expect(mockShowError).toHaveBeenCalledWith({
          title: 'Verification failed',
          description: 'Unknown error',
        })
      })
      expect(mockShowSuccess).not.toHaveBeenCalled()
    })

    it('zeros validationErrorCount on backend error without validation_result and no frontend errors', async () => {
      mockGetState.mockReturnValue(workflowState)
      mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
      mockPost.mockResolvedValue({
        data: undefined,
        error: { title: 'Server Error', detail: 'Internal server error' },
        response: { ok: false },
      })

      const { result } = renderVerificationHook()

      act(() => result.current.handleVerify())

      await waitFor(() => {
        expect(mockSetValidationErrorCount).toHaveBeenCalledWith(0)
        expect(mockDispatch).toHaveBeenCalledWith({ type: 'CLEAR_VALIDATION_ERRORS' })
      })
    })

    it('returns validationErrorCount from the store', () => {
      const { result } = renderVerificationHook()

      expect(result.current.validationErrorCount).toBe(0)
    })
  })
})

describe('silent mode', () => {
  function renderVerificationHook() {
    return renderHook(() => useWorkflowVerification({ dispatch: mockDispatch }))
  }

  const workflowState = {
    currentWorkflow: {
      name: 'Test',
      description: 'desc',
      workflow: { activities: [] },
      triggers: [{ type: 'manual_trigger', id: 't1' }],
    },
    edges: [],
    nodePositions: {},
    _positionsUserModified: false,
  }

  it('does not show error toast in silent mode when backend returns error without validation_result', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: undefined,
      error: { title: 'Server Error', detail: 'Internal server error' },
      response: { ok: false },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerifySilent())

    await waitFor(() => {
      expect(mockShowError).not.toHaveBeenCalled()
      expect(mockShowSuccess).not.toHaveBeenCalled()
    })
  })

  it('does not show success toast in silent mode when workflow is valid', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: { is_valid: true, findings: [] },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerifySilent())

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalledWith({ type: 'CLEAR_VALIDATION_ERRORS' })
      expect(mockShowSuccess).not.toHaveBeenCalled()
    })
  })

  it('does not show error toast in silent mode when fetch rejects', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockRejectedValue(new Error('Network error'))

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerifySilent())

    await waitFor(() => {
      expect(mockShowError).not.toHaveBeenCalled()
    })
  })
})

describe('frontend and backend error merging', () => {
  function renderVerificationHook() {
    return renderHook(() => useWorkflowVerification({ dispatch: mockDispatch }))
  }

  const workflowState = {
    currentWorkflow: {
      name: 'Test',
      description: 'desc',
      workflow: {
        activities: [{ type: 'script', id: 'n1', name: 'Step 1', parameters: {} }],
      },
      triggers: [{ type: 'manual_trigger', id: 't1' }],
    },
    edges: [{ id: 'e1', source: 't1', target: 'n1' }],
    nodePositions: {},
    _positionsUserModified: false,
  }

  it('merges frontend errors with backend errors', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockValidateWorkflow.mockReturnValue({
      errors: [{ message: 'Dangling node', nodeId: 'n1', severity: 'error' }],
    })
    mockPost.mockResolvedValue({
      data: {
        is_valid: false,
        findings: [{ message: 'Graph cycle detected', node_id: null }],
      },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      const setCall = mockDispatch.mock.calls.find(
        (call) => (call[0] as { type: string }).type === 'SET_VALIDATION_ERRORS'
      )
      expect(setCall).toBeDefined()
      const payload = (setCall![0] as { payload: Array<{ message: string }> }).payload
      expect(payload).toHaveLength(2)
      expect(payload[0].message).toBe('Dangling node')
      expect(payload[1].message).toBe('Graph cycle detected')
    })
  })

  it('dispatches frontend errors when backend returns error without validation_result', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockValidateWorkflow.mockReturnValue({
      errors: [{ message: 'Dangling node', nodeId: 'n1', severity: 'error' }],
    })
    mockPost.mockResolvedValue({
      data: undefined,
      error: { title: 'Server Error', detail: 'Internal server error' },
      response: { ok: false },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      const setCall = mockDispatch.mock.calls.find(
        (call) => (call[0] as { type: string }).type === 'SET_VALIDATION_ERRORS'
      )
      expect(setCall).toBeDefined()
      const payload = (setCall![0] as { payload: Array<{ message: string }> }).payload
      expect(payload).toHaveLength(1)
      expect(payload[0].message).toBe('Dangling node')
      expect(mockSetValidationErrorCount).toHaveBeenCalledWith(1)
      expect(mockShowError).toHaveBeenCalledWith({
        title: 'Verification failed',
        description: 'Unknown error',
      })
    })
  })

  it('dispatches frontend errors when fetch rejects', async () => {
    mockGetState.mockReturnValue(workflowState)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockValidateWorkflow.mockReturnValue({
      errors: [{ message: 'Dangling node', nodeId: 'n1', severity: 'error' }],
    })
    mockPost.mockRejectedValue(new Error('Network error'))

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      const setCall = mockDispatch.mock.calls.find(
        (call) => (call[0] as { type: string }).type === 'SET_VALIDATION_ERRORS'
      )
      expect(setCall).toBeDefined()
      expect(mockSetValidationErrorCount).toHaveBeenCalledWith(1)
    })
  })
})

describe('extractValidationErrors', () => {
  it('extracts errors from validation_result findings', () => {
    const err = {
      validation_result: {
        findings: [
          { message: 'Error 1', node_id: 'node-1' },
          { message: 'Error 2', node_id: null },
        ],
      },
    }
    const result = extractValidationErrors(err)
    expect(result).toEqual([
      { message: 'Error 1', nodeId: 'node-1', severity: 'error', fieldPath: null },
      { message: 'Error 2', nodeId: null, severity: 'error', fieldPath: null },
    ])
  })

  it('returns null when no validation_result', () => {
    expect(extractValidationErrors({ title: 'Error' })).toBeNull()
  })

  it('returns null for undefined input', () => {
    expect(extractValidationErrors(undefined)).toBeNull()
  })

  it('returns empty array when validation_result has empty findings', () => {
    expect(extractValidationErrors({ validation_result: { findings: [] } })).toEqual([])
  })

  it('returns null when validation_result has no findings field', () => {
    expect(extractValidationErrors({ validation_result: { is_valid: false } })).toBeNull()
  })

  it('maps severity from findings', () => {
    const err = {
      validation_result: {
        findings: [
          { message: 'Some warning', node_id: 'node-5', severity: 'warning' },
          { message: 'Some error', node_id: null },
        ],
      },
    }
    const result = extractValidationErrors(err)
    expect(result).toEqual([
      { message: 'Some warning', nodeId: 'node-5', severity: 'warning', fieldPath: null },
      { message: 'Some error', nodeId: null, severity: 'error', fieldPath: null },
    ])
  })
})

describe('extractValidationErrorsFromUnknown', () => {
  it('reads validation_result from the top-level error body', () => {
    mockGetState.mockReturnValue({
      currentWorkflow: {
        workflow: {
          activities: [{ id: 'script3', name: 'Orphan Script', type: 'script' }],
        },
      },
    })
    const result = extractValidationErrorsFromUnknown({
      detail: 'The workflow definition failed validation',
      validation_result: {
        findings: [{ message: "Node 'script3' is unreachable from any trigger", node_id: 'script3' }],
      },
    })
    expect(result).toEqual([
      expect.objectContaining({
        message: 'Step "Orphan Script" is unreachable from any trigger',
        nodeId: 'script3',
        nodeName: 'Orphan Script',
      }),
    ])
  })

  it('keeps raw node ids in findings when the activity name is unknown', () => {
    mockGetState.mockReturnValue({ currentWorkflow: { workflow: { activities: [] } } })
    const result = extractValidationErrorsFromUnknown({
      detail: 'The workflow definition failed validation',
      validation_result: {
        findings: [{ message: "Node 'script3' is unreachable from any trigger", node_id: 'script3' }],
      },
    })
    expect(result).toEqual([
      expect.objectContaining({
        message: "Node 'script3' is unreachable from any trigger",
        nodeId: 'script3',
      }),
    ])
  })

  it('unwraps openapi-fetch cause wrappers', () => {
    const result = extractValidationErrorsFromUnknown({
      cause: {
        detail: 'The workflow definition failed validation',
        validation_result: {
          findings: [{ message: 'Step is not connected', node_id: 'n1' }],
        },
      },
    })
    expect(result?.[0]?.message).toBe('Step is not connected')
  })

  it('returns null when no nested validation_result is present', () => {
    expect(extractValidationErrorsFromUnknown({ detail: 'boom' })).toBeNull()
    expect(extractValidationErrorsFromUnknown(undefined)).toBeNull()
  })
})

describe('verification of incomplete nodes', () => {
  function renderVerificationHook() {
    return renderHook(() => useWorkflowVerification({ dispatch: mockDispatch }))
  }

  const workflowWithNodes = {
    currentWorkflow: {
      name: 'Test',
      description: 'desc',
      workflow: {
        activities: [
          { id: 'script-1', name: 'Empty Script', type: 'script', parameters: {} },
          { id: 'script-2', name: 'Empty Script2', type: 'script', parameters: {} },
        ],
      },
      triggers: [{ id: 'trigger-1', type: 'manual_trigger', parameters: {} }],
    },
    edges: [
      { id: 'e1', source: 'trigger-1', target: 'script-1' },
      { id: 'e2', source: 'script-1', target: 'script-2' },
    ],
    nodePositions: {},
    _positionsUserModified: false,
  }

  it('dispatches per-node errors for multiple incomplete nodes', async () => {
    mockGetState.mockReturnValue(workflowWithNodes)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: {
        is_valid: false,
        findings: [
          { message: 'Node configuration is incomplete', node_id: 'script-1' },
          { message: 'Node configuration is incomplete', node_id: 'script-2' },
        ],
      },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalledWith({
        type: 'SET_VALIDATION_ERRORS',
        payload: [
          {
            message: 'Node configuration is incomplete',
            nodeId: 'script-1',
            nodeName: 'Empty Script',
            severity: 'error',
            fieldPath: null,
          },
          {
            message: 'Node configuration is incomplete',
            nodeId: 'script-2',
            nodeName: 'Empty Script2',
            severity: 'error',
            fieldPath: null,
          },
        ],
      })
      expect(mockSetValidationErrorCount).toHaveBeenCalledWith(2)
    })
  })

  it('dispatches errors and warnings separately for incomplete nodes', async () => {
    mockGetState.mockReturnValue(workflowWithNodes)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: {
        is_valid: false,
        findings: [
          { message: 'Missing required field: code', node_id: 'script-1', severity: 'error' },
          { message: 'Script has no error handling', node_id: 'script-2', severity: 'warning' },
        ],
      },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockDispatch).toHaveBeenCalledWith({
        type: 'SET_VALIDATION_ERRORS',
        payload: [
          {
            message: 'Missing required field: code',
            nodeId: 'script-1',
            nodeName: 'Empty Script',
            severity: 'error',
            fieldPath: null,
          },
          {
            message: 'Script has no error handling',
            nodeId: 'script-2',
            nodeName: 'Empty Script2',
            severity: 'warning',
            fieldPath: null,
          },
        ],
      })
      expect(mockSetValidationErrorCount).toHaveBeenCalledWith(2)
    })
  })

  it('sets validationErrorCount to total number of issues from backend', async () => {
    mockGetState.mockReturnValue(workflowWithNodes)
    mockBuildDefinition.mockReturnValue({ nodes: [], edges: [], triggers: [] })
    mockPost.mockResolvedValue({
      data: {
        is_valid: false,
        findings: [
          { message: 'Error 1', node_id: 'script-1' },
          { message: 'Error 2', node_id: 'script-2' },
          { message: 'Global error', node_id: null },
        ],
      },
      error: undefined,
      response: { ok: true },
    })

    const { result } = renderVerificationHook()

    act(() => result.current.handleVerify())

    await waitFor(() => {
      expect(mockSetValidationErrorCount).toHaveBeenCalledWith(3)
    })
  })
})
