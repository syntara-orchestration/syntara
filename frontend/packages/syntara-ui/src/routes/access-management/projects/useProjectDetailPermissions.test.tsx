import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../../access/accessClient'

import { useProjectDetailPermissions } from './useProjectDetailPermissions'

vi.mock('../../access/accessClient', () => ({
  accessFetchClient: { POST: vi.fn() },
}))

vi.mock('../../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useProjectDetailPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns canReadWorkflows and canReadAssignments true when granted for the project', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useProjectDetailPermissions('proj-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canReadWorkflows).toBe(true)
    expect(result.current.canReadAssignments).toBe(true)
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'workflow', resource_project: 'proj-1' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'role-assignment', resource_project: 'proj-1' },
    })
  })

  it('returns canReadWorkflows false when denied', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((_path, opts) => {
      const body = (opts as { body?: { resource_type?: string } }).body
      const allowed = body?.resource_type !== 'workflow'
      return Promise.resolve({ data: { allowed } })
    })

    const { result } = renderHook(() => useProjectDetailPermissions('proj-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canReadWorkflows).toBe(false)
    expect(result.current.canReadAssignments).toBe(true)
  })

  it('returns canReadAssignments false when denied', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((_path, opts) => {
      const body = (opts as { body?: { resource_type?: string } }).body
      const allowed = body?.resource_type !== 'role-assignment'
      return Promise.resolve({ data: { allowed } })
    })

    const { result } = renderHook(() => useProjectDetailPermissions('proj-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.canReadWorkflows).toBe(true)
    expect(result.current.canReadAssignments).toBe(false)
  })

  it('defaults to safe false while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useProjectDetailPermissions('proj-1'), {
      wrapper: createWrapper(),
    })

    expect(result.current.canReadWorkflows).toBe(false)
    expect(result.current.canReadAssignments).toBe(false)
    expect(result.current.isLoading).toBe(true)
  })
})
