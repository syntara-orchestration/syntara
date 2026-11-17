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

import { useFormPromptSubmitUsers } from './useFormPromptSubmitUsers'

const mockPOST = vi.mocked(accessFetchClient.POST)

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryDelay: 0 },
    },
  })
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

describe('useFormPromptSubmitUsers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('scopes who_can to form_prompt submit in the project', async () => {
    mockPOST.mockResolvedValue({
      data: { resources: [], next: null },
      error: undefined,
    })

    renderHook(() => useFormPromptSubmitUsers('project-123'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(mockPOST).toHaveBeenCalled()
    })

    expect(mockPOST).toHaveBeenCalledWith('/authz/who_can', {
      body: expect.objectContaining({
        action: 'submit',
        resource_type: 'form_prompt',
        resource_project: 'project-123',
        sort: 'username',
      }) as Record<string, unknown>,
    })
  })
})
