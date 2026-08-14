import type { IdentityProvidersAPI } from '@syntara/contracts'
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { identityProvidersClient } from '../../../client'
import { useMutationErrorHandler } from '../../../hooks/useMutationErrorHandler'

import { useIdentityProviderToggle } from './useIdentityProviderToggle'

vi.mock('../../../client', () => ({
  identityProvidersClient: {
    useMutation: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../../hooks/useMutationErrorHandler', () => ({
  useMutationErrorHandler: vi.fn(),
}))

type IdentityProvider = IdentityProvidersAPI.components['schemas']['IdentityProviderRead']

const enabledProvider = {
  id: 'idp-1',
  name: 'Test Provider',
  enabled: true,
  configuration: { issuer_url: 'https://example.com', client_id: 'client-1' },
} as IdentityProvider

const disabledProvider = {
  id: 'idp-2',
  name: 'Disabled Provider',
  enabled: false,
  configuration: { issuer_url: 'https://example.com', client_id: 'client-2' },
} as IdentityProvider

function getMutationCallbacks(mockFn: ReturnType<typeof vi.fn>) {
  const lastCall = mockFn.mock.calls.at(-1) as unknown[]
  return (lastCall?.[1] ?? {}) as Record<string, (arg?: unknown) => void>
}

describe('useIdentityProviderToggle', () => {
  const mockPatchMutate = vi.fn()
  const mockOnSuccess = vi.fn()
  const mockErrorHandler = vi.fn()

  beforeEach(() => {
    vi.mocked(identityProvidersClient.useMutation).mockReturnValue({
      mutate: mockPatchMutate,
      isPending: false,
    } as never)
    mockErrorHandler.mockReturnValue(vi.fn())
    vi.mocked(useMutationErrorHandler).mockReturnValue(mockErrorHandler)
    mockPatchMutate.mockClear()
    mockOnSuccess.mockClear()
    mockErrorHandler.mockClear()
    mockErrorHandler.mockReturnValue(vi.fn())
  })

  it('opens disable dialog when toggling an enabled provider', () => {
    const { result } = renderHook(() => useIdentityProviderToggle(mockOnSuccess))

    act(() => {
      result.current.handleToggleEnabled(enabledProvider)
    })

    expect(result.current.disableDialog.isOpen).toBe(true)
    expect(result.current.disableDialog.item).toBe(enabledProvider)
    expect(mockPatchMutate).not.toHaveBeenCalled()
  })

  it('directly enables a disabled provider without dialog', () => {
    const { result } = renderHook(() => useIdentityProviderToggle(mockOnSuccess))

    act(() => {
      result.current.handleToggleEnabled(disabledProvider)
    })

    expect(result.current.disableDialog.isOpen).toBe(false)
    expect(mockPatchMutate).toHaveBeenCalledWith(
      { params: { path: { provider_id: 'idp-2' } }, body: { enabled: true } },
      expect.objectContaining({ onSuccess: expect.any(Function) as unknown })
    )
  })

  it('calls onSuccess when enabling', () => {
    const { result } = renderHook(() => useIdentityProviderToggle(mockOnSuccess))

    act(() => {
      result.current.handleToggleEnabled(disabledProvider)
    })

    act(() => {
      getMutationCallbacks(mockPatchMutate).onSuccess?.()
    })

    expect(mockOnSuccess).toHaveBeenCalled()
  })

  it('uses useMutationErrorHandler for enable errors', () => {
    const { result } = renderHook(() => useIdentityProviderToggle(mockOnSuccess))

    act(() => {
      result.current.handleToggleEnabled(disabledProvider)
    })

    expect(mockErrorHandler).toHaveBeenCalledWith({ title: 'Failed to enable identity provider' })
    expect(mockPatchMutate).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ onError: expect.any(Function) as unknown })
    )
  })

  it('calls patchProvider on confirm disable', () => {
    const { result } = renderHook(() => useIdentityProviderToggle(mockOnSuccess))

    act(() => {
      result.current.handleToggleEnabled(enabledProvider)
    })

    act(() => {
      result.current.handleConfirmDisable()
    })

    expect(mockPatchMutate).toHaveBeenCalledWith(
      { params: { path: { provider_id: 'idp-1' } }, body: { enabled: false } },
      expect.objectContaining({ onSuccess: expect.any(Function) as unknown })
    )
  })

  it('closes dialog and calls onSuccess after disabling', () => {
    const { result } = renderHook(() => useIdentityProviderToggle(mockOnSuccess))

    act(() => {
      result.current.handleToggleEnabled(enabledProvider)
    })

    act(() => {
      result.current.handleConfirmDisable()
    })

    act(() => {
      getMutationCallbacks(mockPatchMutate).onSuccess?.()
      getMutationCallbacks(mockPatchMutate).onSettled?.()
    })

    expect(mockOnSuccess).toHaveBeenCalled()
    expect(result.current.disableDialog.isOpen).toBe(false)
    expect(result.current.isDisabling).toBe(false)
  })

  it('does nothing when provider has no id', () => {
    const { result } = renderHook(() => useIdentityProviderToggle(mockOnSuccess))
    const noIdProvider = { ...enabledProvider, id: undefined } as IdentityProvider

    act(() => {
      result.current.handleToggleEnabled(noIdProvider)
    })

    expect(result.current.disableDialog.isOpen).toBe(false)
    expect(mockPatchMutate).not.toHaveBeenCalled()
  })
})
