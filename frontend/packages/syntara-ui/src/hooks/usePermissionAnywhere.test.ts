import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../routes/access/accessClient'

import { usePermissionAnywhere } from './usePermissionAnywhere'

vi.mock('../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../routes/access/accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('usePermissionAnywhere', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns true when can_i with check_any_project allows', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => usePermissionAnywhere('read', 'role-assignment'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.allowed).toBe(true)
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'role-assignment', check_any_project: true },
    })
  })

  it('returns false when can_i denies', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: false } })

    const { result } = renderHook(() => usePermissionAnywhere('read', 'role-assignment'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })
    expect(result.current.allowed).toBe(false)
  })
})
