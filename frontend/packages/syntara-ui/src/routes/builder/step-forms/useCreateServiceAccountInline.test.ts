import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessClient } from '../../access/accessClient'

import { useCreateServiceAccountInline } from './useCreateServiceAccountInline'

vi.mock('../../access/accessClient', () => ({
  accessClient: {
    useMutation: vi.fn(),
  },
}))

vi.mock('../../../hooks/useFormMutationErrorHandler', () => ({
  useFormMutationErrorHandler: () => () => vi.fn(),
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => QueryClientProvider({ client: queryClient, children })

function setupMocks(overrides?: { saReject?: boolean; credReject?: boolean }) {
  const createSA = overrides?.saReject
    ? vi.fn().mockRejectedValue(new Error('SA failed'))
    : vi.fn().mockResolvedValue({ id: 'new-sa-id', name: 'test-sa' })

  const createCred = overrides?.credReject
    ? vi.fn().mockRejectedValue(new Error('Cred failed'))
    : vi
        .fn()
        .mockResolvedValue({ identifier: 'nx_sa_abc', client_secret: 'secret', expires_at: '2026-12-31T00:00:00Z' })

  let callCount = 0
  vi.mocked(accessClient.useMutation).mockImplementation(() => {
    callCount++
    return (
      callCount % 2 === 1 ? { mutateAsync: createSA, isPending: false } : { mutateAsync: createCred, isPending: false }
    ) as never
  })

  return { createSA, createCred }
}

const formData = { name: 'test-sa', description: '', project_id: '00000000-0000-0000-0000-000000000001' }
const handleError = (() => vi.fn()) as ReturnType<
  typeof import('../../../hooks/useFormMutationErrorHandler').useFormMutationErrorHandler
>

describe('useCreateServiceAccountInline', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('starts with no credentials and not pending', () => {
    setupMocks()
    const { result } = renderHook(() => useCreateServiceAccountInline('2026-12-31'), { wrapper })

    expect(result.current.credentials).toBeNull()
    expect(result.current.showCredentials).toBe(false)
    expect(result.current.isPending).toBe(false)
    expect(result.current.savedAck).toBe(false)
  })

  it('sets credentials after successful submission', async () => {
    const { createSA, createCred } = setupMocks()
    const { result } = renderHook(() => useCreateServiceAccountInline('2026-12-31'), { wrapper })

    await act(async () => {
      await result.current.submitForm(formData, handleError)
    })

    expect(createSA).toHaveBeenCalledWith({
      body: { name: 'test-sa', description: '', project_id: '00000000-0000-0000-0000-000000000001' },
    })
    expect(createCred).toHaveBeenCalledWith({
      params: { path: { service_account_id: 'new-sa-id' } },
      body: { credential_type: 'client_credentials', expires_at: '2026-12-31T00:00:00Z' },
    })
    expect(result.current.credentials).toEqual({
      identifier: 'nx_sa_abc',
      client_secret: 'secret',
      expiresAt: '2026-12-31T00:00:00Z',
    })
    expect(result.current.showCredentials).toBe(true)
    expect(result.current.createdSaId).toBe('new-sa-id')
  })

  it('handles SA creation failure', async () => {
    setupMocks({ saReject: true })
    const errorHandler = vi.fn()
    const mockHandleError = (() => errorHandler) as typeof handleError
    const { result } = renderHook(() => useCreateServiceAccountInline('2026-12-31'), { wrapper })

    await act(async () => {
      await result.current.submitForm(formData, mockHandleError)
    })

    expect(errorHandler).toHaveBeenCalled()
    expect(result.current.credentials).toBeNull()
  })

  it('sets createdSaId before credential creation (orphan-safe)', async () => {
    setupMocks({ credReject: true })
    const errorHandler = vi.fn()
    const mockHandleError = (() => errorHandler) as typeof handleError
    const { result } = renderHook(() => useCreateServiceAccountInline('2026-12-31'), { wrapper })

    await act(async () => {
      await result.current.submitForm(formData, mockHandleError)
    })

    expect(result.current.createdSaId).toBe('new-sa-id')
    expect(result.current.credentials).toBeNull()
    expect(errorHandler).toHaveBeenCalled()
  })

  it('toggles savedAck', () => {
    setupMocks()
    const { result } = renderHook(() => useCreateServiceAccountInline('2026-12-31'), { wrapper })

    act(() => result.current.setSavedAck(true))
    expect(result.current.savedAck).toBe(true)

    act(() => result.current.setSavedAck(false))
    expect(result.current.savedAck).toBe(false)
  })

  it('resetState clears all state and returns saId', async () => {
    setupMocks()
    const { result } = renderHook(() => useCreateServiceAccountInline('2026-12-31'), { wrapper })

    await act(async () => {
      await result.current.submitForm(formData, handleError)
    })

    expect(result.current.createdSaId).toBe('new-sa-id')

    let returnedId: string | null = null
    act(() => {
      returnedId = result.current.resetState()
    })

    expect(returnedId).toBe('new-sa-id')
    expect(result.current.credentials).toBeNull()
    expect(result.current.createdSaId).toBeNull()
    expect(result.current.savedAck).toBe(false)
  })

  it('handles null client_secret in credential response', async () => {
    const createSA = vi.fn().mockResolvedValue({ id: 'new-sa-id', name: 'test-sa' })
    const createCred = vi.fn().mockResolvedValue({
      identifier: 'nx_sa_abc',
      client_secret: null,
      expires_at: null,
    })

    let callCount = 0
    vi.mocked(accessClient.useMutation).mockImplementation(() => {
      callCount++
      return (
        callCount % 2 === 1
          ? { mutateAsync: createSA, isPending: false }
          : { mutateAsync: createCred, isPending: false }
      ) as never
    })

    const { result } = renderHook(() => useCreateServiceAccountInline('2026-12-31'), { wrapper })

    await act(async () => {
      await result.current.submitForm(formData, handleError)
    })

    expect(result.current.credentials).toEqual({
      identifier: 'nx_sa_abc',
      client_secret: '',
      expiresAt: null,
    })
  })

  it('handles undefined description in form data', async () => {
    const { createSA } = setupMocks()
    const { result } = renderHook(() => useCreateServiceAccountInline('2026-12-31'), { wrapper })

    const dataWithNoDesc = { name: 'test-sa', project_id: '00000000-0000-0000-0000-000000000001' } as typeof formData

    await act(async () => {
      await result.current.submitForm(dataWithNoDesc, handleError)
    })

    expect(createSA).toHaveBeenCalledWith({
      body: { name: 'test-sa', description: undefined, project_id: '00000000-0000-0000-0000-000000000001' },
    })
  })

  it('does not send expires_at when expiresAt is empty', async () => {
    const { createCred } = setupMocks()
    const { result } = renderHook(() => useCreateServiceAccountInline(''), { wrapper })

    await act(async () => {
      await result.current.submitForm(formData, handleError)
    })

    const credCallArgs = createCred.mock.calls[0][0] as unknown as { body: Record<string, unknown> }
    expect(credCallArgs.body).not.toHaveProperty('expires_at')
  })
})
