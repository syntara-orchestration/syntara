import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { tanstackRouter } from '../../../../app/tanstackRouter'

import type { IntegrationFormData } from './integrationFormSchema'
import { useCreateIntegration } from './useCreateIntegration'

const mockShowAlert = vi.fn()
const mockCreateMutation = vi.fn()
const mockSyncAssignments = vi.fn()
const mockHandleError = vi.fn(() => vi.fn())

vi.mock('../../../../app/tanstackRouter', () => ({
  tanstackRouter: { navigate: vi.fn().mockResolvedValue(undefined) },
}))

vi.mock('../../../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({ showAlert: mockShowAlert })),
}))

vi.mock('../../../../client', () => ({
  integrationsClient: {
    useMutation: vi.fn(() => ({ mutateAsync: mockCreateMutation })),
  },
}))

vi.mock('../useProjectAssignmentSync', () => ({
  useProjectAssignmentSync: () => ({ syncAssignments: mockSyncAssignments }),
}))

const mockInvalidateQueries = vi.fn().mockResolvedValue(undefined)
const mockFetchQuery = vi.fn().mockResolvedValue(false)
const mockQueryClient = { invalidateQueries: mockInvalidateQueries, fetchQuery: mockFetchQuery }
vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual('@tanstack/react-query')
  return { ...actual, useQueryClient: () => mockQueryClient }
})

vi.mock('./useOpenShiftIntegrationExists', async () => {
  const actual = await vi.importActual<typeof import('./useOpenShiftIntegrationExists')>(
    './useOpenShiftIntegrationExists'
  )
  return {
    ...actual,
    fetchOpenShiftIntegrationExists: vi.fn().mockResolvedValue(false),
  }
})

function createTestFormData(overrides?: Partial<IntegrationFormData>): IntegrationFormData {
  return {
    name: 'Test Integration',
    description: 'Test description',
    integration_type: 'mcp_server',
    configuration: {
      integration_type: 'mcp_server',
      base_url: 'http://localhost:8765/mcp',
    },
    management_credential_id: null,
    scope: 'global',
    project_ids: [],
    ...overrides,
  } as IntegrationFormData
}

describe('useCreateIntegration', () => {
  beforeEach(() => {
    vi.mocked(tanstackRouter.navigate).mockClear()
    mockShowAlert.mockClear()
    mockCreateMutation.mockClear().mockResolvedValue({ id: 'new-id', name: 'Test Integration' })
    mockSyncAssignments.mockClear().mockResolvedValue({ added: [], removed: [], errors: [] })
    mockHandleError.mockClear()
    mockHandleError.mockReturnValue(vi.fn())
    mockInvalidateQueries.mockClear()
    mockFetchQuery.mockClear().mockResolvedValue(false)
  })

  it('creates integration with correct body', async () => {
    const formData = createTestFormData()
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockCreateMutation).toHaveBeenCalledOnce()
    })
    const [reqArg] = mockCreateMutation.mock.calls[0] as [Record<string, unknown>]
    expect(reqArg.body).toMatchObject({
      name: 'Test Integration',
      integration_type: 'mcp_server',
      configuration: { integration_type: 'mcp_server', base_url: 'http://localhost:8765/mcp' },
      scope: 'global',
    })
  })

  it('shows success alert and navigates on create', async () => {
    const formData = createTestFormData()
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockShowAlert).toHaveBeenCalledWith({
        title: 'Integration created',
        description: '"Test Integration" has been saved.',
        variant: 'success',
        autoDismiss: true,
      })
    })
    expect(vi.mocked(tanstackRouter.navigate)).toHaveBeenCalledWith(
      expect.objectContaining({ to: '/configuration/integrations' })
    )
  })

  it('invalidates the openshift existence query after create', async () => {
    const formData = createTestFormData()
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockInvalidateQueries).toHaveBeenCalledWith({
        queryKey: ['openshift-integration-exists'],
      })
    })
  })

  it('handles creation error without navigating', async () => {
    const formData = createTestFormData()
    const mockErrorCallback = vi.fn()
    mockHandleError.mockReturnValue(mockErrorCallback)
    const creationError = new Error('Duplicate name')
    mockCreateMutation.mockRejectedValueOnce(creationError)

    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockErrorCallback).toHaveBeenCalledWith(creationError)
    })
    expect(vi.mocked(tanstackRouter.navigate)).not.toHaveBeenCalled()
  })

  it('passes discovered_tools to the API when provided', async () => {
    const formData = createTestFormData()
    const discoveredTools = [
      { name: 'get_repo', description: 'Get repo details', enabled: true },
      { name: 'create_pr', description: 'Create a PR', enabled: false },
    ]
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData, discoveredTools)
    })

    await waitFor(() => {
      expect(mockCreateMutation).toHaveBeenCalledOnce()
    })
    const [reqArg] = mockCreateMutation.mock.calls[0] as [Record<string, unknown>]
    expect(reqArg.body).toMatchObject({
      discovered_tools: discoveredTools,
    })
  })

  it('passes null discovered_tools when none provided', async () => {
    const formData = createTestFormData()
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockCreateMutation).toHaveBeenCalledOnce()
    })
    const [reqArg] = mockCreateMutation.mock.calls[0] as [Record<string, unknown>]
    expect(reqArg.body).toMatchObject({
      discovered_tools: null,
    })
  })

  it('passes empty description through to the API', async () => {
    const formData = createTestFormData({ description: '' })
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockCreateMutation).toHaveBeenCalledOnce()
    })
    const [reqArg] = mockCreateMutation.mock.calls[0] as [Record<string, unknown>]
    expect(reqArg.body).toMatchObject({
      description: '',
    })
  })

  it('passes management_credential_id when provided', async () => {
    const formData = createTestFormData({ management_credential_id: 'cred-123' })
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockCreateMutation).toHaveBeenCalledOnce()
    })
    const [reqArg] = mockCreateMutation.mock.calls[0] as [Record<string, unknown>]
    expect(reqArg.body).toMatchObject({
      management_credential_id: 'cred-123',
    })
  })

  it('returns a stable function reference across re-renders', () => {
    const { result, rerender } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))
    const firstRef = result.current
    rerender()
    expect(result.current).toBe(firstRef)
  })

  it('passes discovered_models to the API when provided', async () => {
    const formData = createTestFormData({
      integration_type: 'llm_provider',
      configuration: {
        integration_type: 'llm_provider',
        provider_hint: 'red_hat_ai',
        base_url: 'https://api.example.com',
        allow_http: false,
        insecure_skip_tls_verify: false,
      },
    })
    const discoveredModels = [
      { model_id: 'm1', name: 'model-1', description: null, enabled: true, is_default: true },
      { model_id: 'm2', name: 'model-2', description: null, enabled: true, is_default: false },
    ]
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData, undefined, discoveredModels)
    })

    await waitFor(() => {
      expect(mockCreateMutation).toHaveBeenCalledOnce()
    })
    const [reqArg] = mockCreateMutation.mock.calls[0] as [Record<string, unknown>]
    expect(reqArg.body).toMatchObject({
      discovered_models: discoveredModels,
      integration_type: 'llm_provider',
    })
  })

  it('passes null discovered_models when none provided for LLM', async () => {
    const formData = createTestFormData({
      integration_type: 'llm_provider',
      configuration: {
        integration_type: 'llm_provider',
        provider_hint: 'openai',
        base_url: '',
        allow_http: false,
        insecure_skip_tls_verify: false,
      },
    })
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockCreateMutation).toHaveBeenCalledOnce()
    })
    const [reqArg] = mockCreateMutation.mock.calls[0] as [Record<string, unknown>]
    expect(reqArg.body).toMatchObject({
      discovered_models: null,
    })
  })

  it('syncs project assignments after creation when scope is project', async () => {
    const formData = createTestFormData({
      scope: 'project',
      project_ids: ['p-001', 'p-002'],
    })
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockSyncAssignments).toHaveBeenCalledWith('new-id', [], ['p-001', 'p-002'])
    })
    expect(mockInvalidateQueries).toHaveBeenCalled()
    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Integration created', variant: 'success' })
    )
  })

  it('does not sync project assignments when scope is global', async () => {
    const formData = createTestFormData({ scope: 'global' })
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockShowAlert).toHaveBeenCalled()
    })
    expect(mockSyncAssignments).not.toHaveBeenCalled()
  })

  it('shows warning when some project assignments fail', async () => {
    mockSyncAssignments.mockResolvedValueOnce({
      added: ['p-001'],
      removed: [],
      errors: ['Failed to assign project p-002'],
    })
    const formData = createTestFormData({
      scope: 'project',
      project_ids: ['p-001', 'p-002'],
    })
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockShowAlert).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Integration created with warnings', variant: 'warning' })
      )
    })
  })

  it('blocks openshift create when an execution plane integration already exists', async () => {
    mockFetchQuery.mockResolvedValueOnce(true)
    const formData = createTestFormData({
      integration_type: 'openshift',
      configuration: {
        integration_type: 'openshift',
        base_url: 'https://api.cluster.example.com:6443',
        allow_http: false,
        insecure_skip_tls_verify: false,
        ca_certificate: null,
      },
    })
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockShowAlert).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Unable to create integration',
          description: 'Only one Execution plane infrastructure integration is supported.',
          variant: 'danger',
        })
      )
    })
    expect(mockCreateMutation).not.toHaveBeenCalled()
    expect(vi.mocked(tanstackRouter.navigate)).not.toHaveBeenCalled()
  })

  it('blocks openshift create when the existence lookup fails', async () => {
    mockFetchQuery.mockRejectedValueOnce(new Error('network'))
    const formData = createTestFormData({
      integration_type: 'openshift',
      configuration: {
        integration_type: 'openshift',
        base_url: 'https://api.cluster.example.com:6443',
        allow_http: false,
        insecure_skip_tls_verify: false,
        ca_certificate: null,
      },
    })
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockShowAlert).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Unable to create integration',
          variant: 'danger',
        })
      )
    })
    expect(mockCreateMutation).not.toHaveBeenCalled()
  })

  it('rechecks openshift existence before create when none exists', async () => {
    mockFetchQuery.mockResolvedValueOnce(false)
    const formData = createTestFormData({
      integration_type: 'openshift',
      configuration: {
        integration_type: 'openshift',
        base_url: 'https://api.cluster.example.com:6443',
        allow_http: false,
        insecure_skip_tls_verify: false,
        ca_certificate: null,
      },
    })
    const { result } = renderHook(() => useCreateIntegration({ handleError: mockHandleError }))

    act(() => {
      result.current(formData)
    })

    await waitFor(() => {
      expect(mockCreateMutation).toHaveBeenCalledOnce()
    })
    expect(mockFetchQuery).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['openshift-integration-exists'] }))
  })
})
