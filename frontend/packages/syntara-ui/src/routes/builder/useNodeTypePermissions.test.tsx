import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { canModifyNodeType, useNodeTypePermissions } from './useNodeTypePermissions'

const mockPost = vi.fn()

vi.mock('../access/accessClient', () => ({
  accessFetchClient: {
    POST: (...args: unknown[]) => mockPost(...args) as Promise<unknown>,
  },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

describe('useNodeTypePermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each([
    [{ read: true, write: true, execute: false }, true],
    [{ read: false, write: true, execute: true }, false],
    [{ read: true, write: false, execute: true }, false],
    [undefined, false],
  ] as const)('requires read and write access for modification: %j', (permission, expected) => {
    expect(canModifyNodeType(permission)).toBe(expected)
  })

  it('fails closed while loading and when projectId is missing', () => {
    const { result } = renderHook(() => useNodeTypePermissions(undefined, ['script']), {
      wrapper: createWrapper(),
    })

    expect(result.current.permissions.script).toEqual({ read: false, write: false, execute: false })
  })

  it('maps allowed results when queries resolve', async () => {
    mockPost.mockImplementation((_path: string, init: { body: { action: string } }) => {
      const allowed = init.body.action !== 'write'
      return Promise.resolve({
        data: { results: [{ node_type: 'script', allowed }] },
        error: undefined,
      })
    })

    const { result } = renderHook(() => useNodeTypePermissions('project-1', ['script']), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.permissions.script).toEqual({ read: true, write: false, execute: true })
  })
})
