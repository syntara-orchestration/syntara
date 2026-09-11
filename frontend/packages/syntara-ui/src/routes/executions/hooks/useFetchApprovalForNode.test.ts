import { act, renderHook } from '@testing-library/react'

import { approvalsClient } from '../../../client'

import { useFetchApprovalForNode } from './useFetchApprovalForNode'

vi.mock('../../../client', () => ({
  approvalsClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

const mockApproval = {
  id: 'approval-1',
  approval_node_id: 'node-abc',
  status: 'pending',
  name: 'Test Approval',
  execution_id: 'exec-1',
}

const mockApprovalOther = {
  id: 'approval-2',
  approval_node_id: 'node-xyz',
  status: 'pending',
  name: 'Other Approval',
  execution_id: 'exec-1',
}

describe('useFetchApprovalForNode', () => {
  const mockRefetch = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      refetch: mockRefetch,
      data: null,
      isPending: false,
      error: null,
      isError: false,
    } as never)
  })

  it('starts with isLoading false', () => {
    const { result } = renderHook(() => useFetchApprovalForNode('exec-1'))

    expect(result.current.isLoading).toBe(false)
  })

  it('fetches and returns matching approval for node', async () => {
    mockRefetch.mockResolvedValue({
      data: { resources: [mockApproval, mockApprovalOther] },
    })

    const { result } = renderHook(() => useFetchApprovalForNode('exec-1'))

    let fetchedApproval: unknown
    await act(async () => {
      fetchedApproval = await result.current.fetchForNode('node-abc')
    })

    expect(fetchedApproval).toEqual(mockApproval)
    expect(result.current.isLoading).toBe(false)
  })

  it('returns null when no matching approval found', async () => {
    mockRefetch.mockResolvedValue({
      data: { resources: [mockApprovalOther] },
    })

    const { result } = renderHook(() => useFetchApprovalForNode('exec-1'))

    let fetchedApproval: unknown
    await act(async () => {
      fetchedApproval = await result.current.fetchForNode('nonexistent-node')
    })

    expect(fetchedApproval).toBeNull()
  })

  it('matches a loop-iteration approval_node_id to the canvas node', async () => {
    mockRefetch.mockResolvedValue({
      data: { resources: [{ ...mockApproval, approval_node_id: 'node-abc_iter_1' }, mockApprovalOther] },
    })

    const { result } = renderHook(() => useFetchApprovalForNode('exec-1'))

    let fetchedApproval: unknown
    await act(async () => {
      fetchedApproval = await result.current.fetchForNode('node-abc')
    })

    expect(fetchedApproval).toMatchObject({ approval_node_id: 'node-abc_iter_1' })
  })

  it('returns null when no approvals exist', async () => {
    mockRefetch.mockResolvedValue({
      data: { resources: [] },
    })

    const { result } = renderHook(() => useFetchApprovalForNode('exec-1'))

    let fetchedApproval: unknown
    await act(async () => {
      fetchedApproval = await result.current.fetchForNode('node-abc')
    })

    expect(fetchedApproval).toBeNull()
  })

  it('resets isLoading on clear', () => {
    const { result } = renderHook(() => useFetchApprovalForNode('exec-1'))

    act(() => {
      result.current.clear()
    })

    expect(result.current.isLoading).toBe(false)
  })

  it('resets isLoading when fetch fails', async () => {
    mockRefetch.mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(() => useFetchApprovalForNode('exec-1'))

    await act(async () => {
      await expect(result.current.fetchForNode('node-abc')).rejects.toThrow('Network error')
    })

    expect(result.current.isLoading).toBe(false)
  })

  it('queries with correct execution_id and pending status', () => {
    renderHook(() => useFetchApprovalForNode('exec-42'))

    expect(approvalsClient.useQuery).toHaveBeenCalledWith('get', '/approvals', {
      params: {
        query: {
          execution_id: 'exec-42',
          status: 'pending',
        },
      },
      enabled: false,
    })
  })

  it('returns null without fetching when executionId is empty', async () => {
    const { result } = renderHook(() => useFetchApprovalForNode(''))

    let fetchedApproval: unknown
    await act(async () => {
      fetchedApproval = await result.current.fetchForNode('node-abc')
    })

    expect(fetchedApproval).toBeNull()
    expect(mockRefetch).not.toHaveBeenCalled()
    expect(result.current.isLoading).toBe(false)
  })
})
