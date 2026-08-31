import type { IntegrationsAPI } from '@syntara/contracts'
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { EditIntegrationFormValues } from './editIntegrationFormSchema'
import { useEditTestConnection } from './useEditTestConnection'

const mockShowAlert = vi.fn()
const mockMutate = vi.fn()

vi.mock('../../../providers/alerts', () => ({
  useAlerts: vi.fn(() => ({ showAlert: mockShowAlert })),
}))

vi.mock('../../../client', () => ({
  integrationsClient: {
    useMutation: vi.fn(() => ({ mutate: mockMutate, isPending: false })),
  },
}))

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

const BASE_INTEGRATION: IntegrationRead = {
  id: 'int-1',
  name: 'Test MCP',
  integration_type: 'mcp_server',
  enabled: true,
  validation_status: 'available',
  scope: 'global',
  configuration: { integration_type: 'mcp_server', base_url: 'https://example.com' },
  management_credential_id: null,
  last_validated_at: null,
  validation_error: null,
  refresh_status: null,
  last_refreshed_at: null,
  refresh_error: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'user-1' },
  labels: {},
}

function makeFormValues(overrides?: Partial<EditIntegrationFormValues>): EditIntegrationFormValues {
  return {
    name: 'Test',
    description: '',
    integration_type: 'mcp_server',
    base_url: 'https://example.com',
    allow_http: false,
    insecure_skip_tls_verify: false,
    scope: 'global',
    project_ids: [],
    management_credential_id: 'cred-1',
    ...overrides,
  }
}

describe('useEditTestConnection', () => {
  beforeEach(() => {
    mockShowAlert.mockClear()
    mockMutate.mockClear()
  })

  it('calls mutate for MCP server without credential (credential not required)', () => {
    const getValues = vi.fn(() => makeFormValues({ management_credential_id: null }))
    const { result } = renderHook(() => useEditTestConnection(BASE_INTEGRATION, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    expect(mockMutate).toHaveBeenCalledOnce()
    const [request] = mockMutate.mock.calls[0] as [{ body: Record<string, unknown> }]
    expect(request.body.credential_id).toBeUndefined()
  })

  it('does not call mutate for LLM provider without credential (credential required)', () => {
    const llmIntegration: IntegrationRead = {
      ...BASE_INTEGRATION,
      integration_type: 'llm_provider',
      configuration: { integration_type: 'llm_provider', provider_hint: 'openai' },
    }
    const getValues = vi.fn(() => makeFormValues({ integration_type: 'llm_provider', management_credential_id: null }))
    const { result } = renderHook(() => useEditTestConnection(llmIntegration, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('does not call mutate when integration is undefined', () => {
    const getValues = vi.fn(() => makeFormValues())
    const { result } = renderHook(() => useEditTestConnection(undefined, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    expect(mockMutate).not.toHaveBeenCalled()
  })

  it('calls mutate with correct body for MCP server', () => {
    const getValues = vi.fn(() => makeFormValues())
    const { result } = renderHook(() => useEditTestConnection(BASE_INTEGRATION, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    expect(mockMutate).toHaveBeenCalledOnce()
    const [request] = mockMutate.mock.calls[0] as [{ body: Record<string, unknown> }]
    expect(request.body).toMatchObject({
      integration_type: 'mcp_server',
      credential_id: 'cred-1',
    })
  })

  it('shows success alert with tool count for MCP server', () => {
    const getValues = vi.fn(() => makeFormValues())
    const { result } = renderHook(() => useEditTestConnection(BASE_INTEGRATION, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    const [, callbacks] = mockMutate.mock.calls[0] as [unknown, { onSuccess: (r: unknown) => void }]
    act(() => {
      callbacks.onSuccess({
        success: true,
        discovered_tools: [
          { name: 'tool-1', description: 'desc' },
          { name: 'tool-2', description: 'desc' },
        ],
        discovered_models: null,
      })
    })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Connection tested',
        description: 'Successfully connected. Discovered 2 tools.',
        variant: 'success',
      })
    )
  })

  it('shows singular tool label when one tool discovered', () => {
    const getValues = vi.fn(() => makeFormValues())
    const { result } = renderHook(() => useEditTestConnection(BASE_INTEGRATION, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    const [, callbacks] = mockMutate.mock.calls[0] as [unknown, { onSuccess: (r: unknown) => void }]
    act(() => {
      callbacks.onSuccess({
        success: true,
        discovered_tools: [{ name: 'tool-1', description: 'desc' }],
        discovered_models: null,
      })
    })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'Successfully connected. Discovered 1 tool.',
      })
    )
  })

  it('shows reachable message when MCP discovers zero tools', () => {
    const getValues = vi.fn(() => makeFormValues())
    const { result } = renderHook(() => useEditTestConnection(BASE_INTEGRATION, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    const [, callbacks] = mockMutate.mock.calls[0] as [unknown, { onSuccess: (r: unknown) => void }]
    act(() => {
      callbacks.onSuccess({ success: true, discovered_tools: [], discovered_models: null })
    })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'Successfully connected. The integration is reachable.',
      })
    )
  })

  it('shows success alert with model count for LLM provider', () => {
    const llmIntegration: IntegrationRead = {
      ...BASE_INTEGRATION,
      integration_type: 'llm_provider',
      configuration: { integration_type: 'llm_provider', provider_hint: 'openai' },
    }
    const getValues = vi.fn(() => makeFormValues({ integration_type: 'llm_provider', base_url: '' }))
    const { result } = renderHook(() => useEditTestConnection(llmIntegration, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    const [, callbacks] = mockMutate.mock.calls[0] as [unknown, { onSuccess: (r: unknown) => void }]
    act(() => {
      callbacks.onSuccess({
        success: true,
        discovered_tools: null,
        discovered_models: [
          { id: 'gpt-4', name: 'GPT-4', description: null },
          { id: 'gpt-3.5', name: 'GPT-3.5', description: null },
          { id: 'gpt-4o', name: 'GPT-4o', description: null },
        ],
      })
    })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Connection tested',
        description: 'Successfully connected. Discovered 3 models.',
        variant: 'success',
      })
    )
  })

  it('shows reachable message for AAP with no resources', () => {
    const aapIntegration: IntegrationRead = {
      ...BASE_INTEGRATION,
      integration_type: 'ansible_automation_platform',
      configuration: { integration_type: 'ansible_automation_platform', base_url: 'https://aap.example.com' },
    }
    const getValues = vi.fn(() =>
      makeFormValues({ integration_type: 'ansible_automation_platform', base_url: 'https://aap.example.com' })
    )
    const { result } = renderHook(() => useEditTestConnection(aapIntegration, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    const [, callbacks] = mockMutate.mock.calls[0] as [unknown, { onSuccess: (r: unknown) => void }]
    act(() => {
      callbacks.onSuccess({ success: true, discovered_tools: null, discovered_models: null })
    })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'Successfully connected. The integration is reachable.',
        variant: 'success',
      })
    )
  })

  it('shows failure alert when result.success is false', () => {
    const getValues = vi.fn(() => makeFormValues())
    const { result } = renderHook(() => useEditTestConnection(BASE_INTEGRATION, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    const [, callbacks] = mockMutate.mock.calls[0] as [unknown, { onSuccess: (r: unknown) => void }]
    act(() => {
      callbacks.onSuccess({ success: false, error: 'Connection refused' })
    })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Connection failed',
        description: 'Connection refused',
        variant: 'danger',
      })
    )
  })

  it('shows default failure message when error is null', () => {
    const getValues = vi.fn(() => makeFormValues())
    const { result } = renderHook(() => useEditTestConnection(BASE_INTEGRATION, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    const [, callbacks] = mockMutate.mock.calls[0] as [unknown, { onSuccess: (r: unknown) => void }]
    act(() => {
      callbacks.onSuccess({ success: false, error: null })
    })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        description: 'Unable to connect to the integration.',
      })
    )
  })

  it('shows error alert on API error', () => {
    const getValues = vi.fn(() => makeFormValues())
    const { result } = renderHook(() => useEditTestConnection(BASE_INTEGRATION, getValues))

    act(() => {
      result.current.handleTestConnection()
    })

    const [, callbacks] = mockMutate.mock.calls[0] as [unknown, { onError: (e: unknown) => void }]
    act(() => {
      callbacks.onError(new Error('Network error'))
    })

    expect(mockShowAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Connection test failed',
        variant: 'danger',
      })
    )
  })
})
