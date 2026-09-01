import type { IntegrationsAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import { integrationsClient } from '../../../client'
import { AlertProvider } from '../../../providers/alerts'
import { routerTestState } from '../../../test/setup'

import { useIntegrationActions } from './useIntegrationActions'

vi.mock('../../../client', () => ({
  integrationsClient: {
    useMutation: vi.fn(),
  },
}))

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

type MockMutationCallbacks = {
  onSuccess?: (...args: unknown[]) => void
  onError?: (error: unknown) => void
  onSettled?: () => void
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <AlertProvider>{children}</AlertProvider>
  </QueryClientProvider>
)

const mockIntegration: IntegrationRead = {
  id: 'int-1',
  name: 'Test Integration',
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
  created_by: 'user-1',
  labels: {},
}

describe('useIntegrationActions', () => {
  const mockMutate = vi.fn()
  const mockRefetch = vi.fn().mockResolvedValue({})

  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(integrationsClient.useMutation).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      mutateAsync: vi.fn(),
      isIdle: true,
      isSuccess: false,
      isError: false,
      error: null,
      data: null,
      reset: vi.fn(),
      failureCount: 0,
      failureReason: null,
      context: undefined,
      submittedAt: 0,
      variables: undefined,
      status: 'idle',
      isPaused: false,
    })
  })

  describe('validateDialog', () => {
    it('starts closed', () => {
      const { result } = renderHook(() => useIntegrationActions(mockRefetch), { wrapper })

      expect(result.current.validateDialog.isOpen).toBe(false)
    })

    it('opens and closes', () => {
      const { result } = renderHook(() => useIntegrationActions(mockRefetch), { wrapper })

      act(() => result.current.validateDialog.open(mockIntegration))
      expect(result.current.validateDialog.isOpen).toBe(true)
      expect(result.current.validateDialog.item?.id).toBe('int-1')

      act(() => result.current.validateDialog.close())
      expect(result.current.validateDialog.isOpen).toBe(false)
    })

    it('handleValidate calls validate mutation', () => {
      const { result } = renderHook(() => useIntegrationActions(mockRefetch), { wrapper })

      act(() => result.current.validateDialog.open(mockIntegration))
      act(() => result.current.handleValidate())

      expect(mockMutate).toHaveBeenCalledWith({ params: { path: { integration_id: 'int-1' } } }, expect.any(Object))
    })

    it('refetches after validation success', () => {
      mockMutate.mockImplementation((_args: unknown, callbacks: MockMutationCallbacks) => {
        callbacks.onSuccess?.({ success: true })
        callbacks.onSettled?.()
      })

      const { result } = renderHook(() => useIntegrationActions(mockRefetch), { wrapper })

      act(() => result.current.validateDialog.open(mockIntegration))
      act(() => result.current.handleValidate())

      expect(mockRefetch).toHaveBeenCalled()
    })

    it('refetches after validation error to update status badge', () => {
      mockMutate.mockImplementation((_args: unknown, callbacks: MockMutationCallbacks) => {
        callbacks.onError?.(new Error('credential required'))
        callbacks.onSettled?.()
      })

      const { result } = renderHook(() => useIntegrationActions(mockRefetch), { wrapper })

      act(() => result.current.validateDialog.open(mockIntegration))
      act(() => result.current.handleValidate())

      expect(mockRefetch).toHaveBeenCalled()
    })
  })

  describe('deleteDialog', () => {
    it('handleDelete calls delete mutation and navigates on success', () => {
      mockMutate.mockImplementation((_args: unknown, callbacks: MockMutationCallbacks) => {
        callbacks.onSuccess?.()
        callbacks.onSettled?.()
      })

      const { result } = renderHook(() => useIntegrationActions(mockRefetch), { wrapper })

      act(() => result.current.deleteDialog.open(mockIntegration))
      act(() => result.current.handleDelete())

      expect(mockMutate).toHaveBeenCalled()
      expect(routerTestState.navigate).toHaveBeenCalled()
    })
  })

  describe('handleToggleEnabled', () => {
    it('opens disable dialog when integration is enabled', () => {
      const { result } = renderHook(() => useIntegrationActions(mockRefetch), { wrapper })

      act(() => result.current.handleToggleEnabled(mockIntegration))

      expect(result.current.disableDialog.isOpen).toBe(true)
    })

    it('patches directly when integration is disabled', () => {
      const disabledIntegration = { ...mockIntegration, enabled: false }
      const { result } = renderHook(() => useIntegrationActions(mockRefetch), { wrapper })

      act(() => result.current.handleToggleEnabled(disabledIntegration))

      expect(mockMutate).toHaveBeenCalledWith(expect.objectContaining({ body: { enabled: true } }), expect.any(Object))
    })
  })

  describe('handleDisable', () => {
    it('patches integration to disabled', () => {
      const { result } = renderHook(() => useIntegrationActions(mockRefetch), { wrapper })

      act(() => result.current.disableDialog.open(mockIntegration))
      act(() => result.current.handleDisable())

      expect(mockMutate).toHaveBeenCalledWith(expect.objectContaining({ body: { enabled: false } }), expect.any(Object))
    })
  })
})
