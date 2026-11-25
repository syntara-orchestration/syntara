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

// Get reference to the mocked POST after the mock is set up
import { accessFetchClient } from '../../access/accessClient'

import { useApprovalDecideUsers } from './useApprovalDecideUsers'

type WhoCanUser = AuthzAPI.components['schemas']['WhoCanUser']

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

describe('useApprovalDecideUsers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches and returns users from authz/who_can endpoint', async () => {
    const mockUsers: WhoCanUser[] = [
      { id: 'user-1', username: 'alice' },
      { id: 'user-2', username: 'bob' },
    ]

    mockPOST.mockResolvedValue({
      data: { resources: mockUsers, next: null },
      error: undefined,
    })

    const { result } = renderHook(() => useApprovalDecideUsers('project-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.users).toEqual(mockUsers)
    expect(result.current.error).toBe(null)
  })

  it('handles loading state', () => {
    mockPOST.mockImplementation(
      () =>
        new Promise(() => {
          /* never resolves */
        })
    )

    const { result } = renderHook(() => useApprovalDecideUsers('project-1'), {
      wrapper: createWrapper(),
    })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.users).toEqual([])
  })

  it('handles error state', async () => {
    const mockError = { message: 'Failed to fetch' }

    mockPOST.mockResolvedValue({
      data: undefined,
      error: mockError,
    })

    const { result } = renderHook(() => useApprovalDecideUsers('project-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.error).toBeTruthy()
    expect(result.current.users).toEqual([])
  })

  it('scopes query to project when projectId provided', async () => {
    mockPOST.mockResolvedValue({
      data: { resources: [], next: null },
      error: undefined,
    })

    renderHook(() => useApprovalDecideUsers('project-123'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(mockPOST).toHaveBeenCalled()
    })

    expect(mockPOST).toHaveBeenCalledWith('/authz/who_can', {
      body: expect.objectContaining({
        action: 'decide',
        resource_type: 'approval',
        resource_project: 'project-123',
        sort: 'username',
      }) as Record<string, unknown>,
    })
  })

  it('does not fetch when projectId is null', () => {
    const { result } = renderHook(() => useApprovalDecideUsers(null), {
      wrapper: createWrapper(),
    })

    expect(mockPOST).not.toHaveBeenCalled()
    expect(result.current.isLoading).toBe(false)
    expect(result.current.users).toEqual([])
  })

  it('does not fetch when projectId is undefined', () => {
    const { result } = renderHook(() => useApprovalDecideUsers(), {
      wrapper: createWrapper(),
    })

    expect(mockPOST).not.toHaveBeenCalled()
    expect(result.current.isLoading).toBe(false)
    expect(result.current.users).toEqual([])
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

    const { result } = renderHook(() => useApprovalDecideUsers('project-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.users).toEqual([...page1Users, ...page2Users])
    expect(mockPOST).toHaveBeenCalledTimes(2)
  })

  it('sets isPermissionDenied when API returns AUTHORIZATION_DENIED', async () => {
    mockPOST.mockResolvedValue({
      data: undefined,
      error: { code: 'AUTHORIZATION_DENIED', title: 'Authorization Denied', detail: 'Not authorized' },
    })

    const { result } = renderHook(() => useApprovalDecideUsers('project-123'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.isPermissionDenied).toBe(true)
    expect(result.current.users).toEqual([])
    expect(result.current.error).toBeNull()
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

    const { result } = renderHook(() => useApprovalDecideUsers('project-1'), { wrapper })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(mockPOST).toHaveBeenCalledTimes(1)
    expect(result.current.isPermissionDenied).toBe(true)
  })

  it('returns empty array when no users have permission', async () => {
    mockPOST.mockResolvedValue({
      data: { resources: [], next: null },
      error: undefined,
    })

    const { result } = renderHook(() => useApprovalDecideUsers('project-1'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.users).toEqual([])
  })
})
