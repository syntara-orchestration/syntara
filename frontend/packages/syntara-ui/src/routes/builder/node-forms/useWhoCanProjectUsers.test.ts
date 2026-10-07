import type { AuthzAPI } from '@syntara/contracts'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../access/accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

import { accessFetchClient } from '../../access/accessClient'

import { useWhoCanProjectUsers } from './useWhoCanProjectUsers'

type WhoCanUser = AuthzAPI.components['schemas']['WhoCanUser']

const mockPOST = vi.mocked(accessFetchClient.POST)

const FORM_PROMPT_WHO_CAN = {
  action: 'submit',
  resourceType: 'form_prompt',
  queryKeyPrefix: 'form-prompt-submit-users',
} as const

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryDelay: 0 },
    },
  })
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

describe('useWhoCanProjectUsers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches all pages when pagination is present', async () => {
    const page1Users: WhoCanUser[] = [
      { id: 'user-1', username: 'alice' },
      { id: 'user-2', username: 'bob' },
    ]
    const page2Users: WhoCanUser[] = [{ id: 'user-3', username: 'charlie' }]

    mockPOST
      .mockResolvedValueOnce({
        data: { resources: page1Users, next: 'cursor-1' },
        error: undefined,
      })
      .mockResolvedValueOnce({
        data: { resources: page2Users, next: null },
        error: undefined,
      })

    const { result } = renderHook(
      () =>
        useWhoCanProjectUsers({
          projectId: 'project-1',
          ...FORM_PROMPT_WHO_CAN,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.users).toEqual([...page1Users, ...page2Users])
    expect(mockPOST).toHaveBeenCalledTimes(2)
  })

  it('does not retry on PermissionDeniedError', async () => {
    mockPOST.mockResolvedValue({
      data: undefined,
      error: { code: 'AUTHORIZATION_DENIED', title: 'Authorization Denied', detail: 'Not authorized' },
    })

    const retryEnabledClient = new QueryClient({
      defaultOptions: {
        queries: { retry: 3 },
      },
    })
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: retryEnabledClient }, children)

    const { result } = renderHook(
      () =>
        useWhoCanProjectUsers({
          projectId: 'project-1',
          ...FORM_PROMPT_WHO_CAN,
        }),
      { wrapper }
    )

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(mockPOST).toHaveBeenCalledTimes(1)
    expect(result.current.isPermissionDenied).toBe(true)
  })

  it('handles loading state', () => {
    mockPOST.mockImplementation(
      () =>
        new Promise(() => {
          /* never resolves */
        })
    )

    const { result } = renderHook(
      () =>
        useWhoCanProjectUsers({
          projectId: 'project-1',
          ...FORM_PROMPT_WHO_CAN,
        }),
      { wrapper: createWrapper() }
    )

    expect(result.current.isLoading).toBe(true)
    expect(result.current.users).toEqual([])
  })

  it('handles error state', async () => {
    mockPOST.mockResolvedValue({
      data: undefined,
      error: { message: 'Failed to fetch' },
    })

    const { result } = renderHook(
      () =>
        useWhoCanProjectUsers({
          projectId: 'project-1',
          ...FORM_PROMPT_WHO_CAN,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
    expect(result.current.users).toEqual([])
  })
})
