import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../routes/access/accessClient'

import { useCanI } from './useCanI'

vi.mock('../routes/access/accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
    use: vi.fn(),
  },
}))

vi.mock('../client', () => ({
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

describe('useCanI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns allowed true when permission is granted', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: { allowed: true },
    })

    const { result } = renderHook(() => useCanI('read', 'setting'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.allowed).toBe(true)
    })

    expect(result.current.isChecking).toBe(false)
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'setting' },
    })
  })

  it('returns allowed false when permission is denied', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: { allowed: false },
    })

    const { result } = renderHook(() => useCanI('write', 'setting'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.allowed).toBe(false)
  })

  it('defaults to allowed false and isChecking true while in flight', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useCanI('delete', 'workflow'), { wrapper: createWrapper() })

    expect(result.current.allowed).toBe(false)
    expect(result.current.isChecking).toBe(true)
  })

  it('returns safe defaults when response has no data', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: undefined })

    const { result } = renderHook(() => useCanI('read', 'setting'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.allowed).toBe(false)
  })

  it('returns safe defaults when request fails', async () => {
    vi.mocked(accessFetchClient.POST).mockRejectedValue(new Error('network error'))

    const { result } = renderHook(() => useCanI('read', 'setting'), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(result.current.allowed).toBe(false)
  })

  it('passes resourceId when provided', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: { allowed: true },
    })

    const { result } = renderHook(() => useCanI('update', 'workflow', { resourceId: 'project:default' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.allowed).toBe(true)
    })

    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'update', resource_type: 'workflow', resource_id: 'project:default' },
    })
  })

  it('passes resource_project when resourceProject is provided', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: { allowed: true },
    })

    const { result } = renderHook(() => useCanI('update', 'workflow', { resourceProject: 'proj-1' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.allowed).toBe(true)
    })

    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'update', resource_type: 'workflow', resource_project: 'proj-1' },
    })
  })

  it('passes resource_labels when resourceLabels are provided', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: false } })

    const { result } = renderHook(() => useCanI('execute', 'workflow_node', { resourceLabels: { kind: 'script' } }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isChecking).toBe(false)
    })

    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'execute', resource_type: 'workflow_node', resource_labels: { kind: 'script' } },
    })
  })

  it('passes check_any_project when checkAnyProject is true', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: { allowed: true },
    })

    const { result } = renderHook(() => useCanI('read', 'role-assignment', { checkAnyProject: true }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.allowed).toBe(true)
    })

    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'role-assignment', check_any_project: true },
    })
  })

  it('prefers resourceProject over checkAnyProject (never sends both)', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: { allowed: true },
    })

    const { result } = renderHook(
      () => useCanI('update', 'service_account', { resourceProject: 'proj-1', checkAnyProject: true }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.allowed).toBe(true)
    })

    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'update', resource_type: 'service_account', resource_project: 'proj-1' },
    })
  })

  it('skips API call when enabled is false', () => {
    const { result } = renderHook(() => useCanI('read', 'setting', { enabled: false }), {
      wrapper: createWrapper(),
    })

    expect(result.current.allowed).toBe(false)
    expect(result.current.isChecking).toBe(false)
    expect(accessFetchClient.POST).not.toHaveBeenCalled()
  })

  it('re-fires when action changes', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({
      data: { allowed: true },
    })

    const wrapper = createWrapper()
    const { result, rerender } = renderHook(({ action }) => useCanI(action, 'workflow'), {
      initialProps: { action: 'read' },
      wrapper,
    })

    await waitFor(() => {
      expect(result.current.allowed).toBe(true)
    })

    rerender({ action: 'delete' })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
        body: { action: 'delete', resource_type: 'workflow' },
      })
    })
  })

  it('deduplicates queries across multiple consumers', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const wrapper = createWrapper()
    renderHook(() => useCanI('read', 'setting'), { wrapper })
    renderHook(() => useCanI('read', 'setting'), { wrapper })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledTimes(1)
    })
  })
})
