import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { invalidateAuthzCaches } from '../../hooks/invalidateAuthzCaches'
import { accessFetchClient } from '../access/accessClient'

import { useStepTypePermissions } from './useStepTypePermissions'

vi.mock('../access/accessClient', () => ({
  accessFetchClient: { POST: vi.fn() },
}))

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useStepTypePermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('checks distinct types in the concrete project and returns display labels', async () => {
    vi.mocked(accessFetchClient.POST).mockImplementation((_path, options) => {
      const body = Reflect.get(options, 'body') as { resource_labels?: { kind?: string } }
      const kind = body.resource_labels?.kind
      return Promise.resolve({ data: { allowed: kind !== 'script' } })
    })

    const { result } = renderHook(() => useStepTypePermissions(['script', 'wait', 'script'], 'project-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isChecking).toBe(false))

    expect(result.current.canAuthor).toBe(false)
    expect(result.current.blockedStepTypes).toEqual([expect.objectContaining({ kind: 'script', label: 'Script' })])
    expect(accessFetchClient.POST).toHaveBeenCalledTimes(2)
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: {
        action: 'write',
        resource_type: 'step_type',
        resource_labels: { kind: 'script' },
        resource_project: 'project-1',
      },
    })
  })

  it('treats an empty summary as valid and missing context as an error', async () => {
    const { result: emptyResult } = renderHook(() => useStepTypePermissions([], 'project-1'), {
      wrapper: createWrapper(),
    })

    expect(emptyResult.current.canAuthor).toBe(true)
    expect(accessFetchClient.POST).not.toHaveBeenCalled()

    const retryContext = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useStepTypePermissions(null, 'project-1', { retryContext }), {
      wrapper: createWrapper(),
    })
    expect(result.current.isError).toBe(true)
    expect(result.current.canAuthor).toBe(false)
    await act(async () => result.current.retry())
    expect(retryContext).toHaveBeenCalledOnce()
  })

  it('can retry a failed permission query', async () => {
    vi.mocked(accessFetchClient.POST)
      .mockRejectedValueOnce(new Error('temporary failure'))
      .mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useStepTypePermissions(['script'], 'project-2'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    await act(async () => result.current.retry())

    await waitFor(() => expect(result.current.canAuthor).toBe(true))
    expect(accessFetchClient.POST).toHaveBeenCalledTimes(2)
  })
  it.each([
    [
      { denied: true, denied_by: 'no-scripts', denied_scope: 'project', denied_project: 'payments' },
      'Script (no-scripts, project payments).',
    ],
    [{ denied: true, denied_by: 'no-scripts', denied_scope: 'any' }, 'Script (no-scripts, all projects).'],
    [
      { denied: false, denied_by: '', denial_reason: 'no_matching_allow', denied_project: 'payments' },
      'No policy grants write permission for Script in project payments.',
    ],
  ])('explains a blocked decision with its provenance: %j', async (decision, description) => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: false, ...decision } })
    const { result } = renderHook(() => useStepTypePermissions(['script'], 'project-1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isChecking).toBe(false))
    expect(result.current.blockedStepTypes[0]?.description).toBe(description)
  })

  it('updates both ways after policy or assignment cache invalidation', async () => {
    let allowed = false
    vi.mocked(accessFetchClient.POST).mockImplementation(() => Promise.resolve({ data: { allowed } }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useStepTypePermissions(['script'], 'project-1'), {
      wrapper: ({ children }) => createElement(QueryClientProvider, { client: queryClient }, children),
    })
    await waitFor(() => expect(result.current.isChecking).toBe(false))
    expect(result.current.canAuthor).toBe(false)
    allowed = true
    act(() => invalidateAuthzCaches(queryClient))
    await waitFor(() => expect(result.current.canAuthor).toBe(true))
    allowed = false
    act(() => invalidateAuthzCaches(queryClient))
    await waitFor(() => expect(result.current.canAuthor).toBe(false))
  })
})
