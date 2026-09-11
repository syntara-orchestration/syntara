import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessClient } from '../routes/access/accessClient'

import { useActiveAdminCount } from './useActiveAdminCount'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../routes/access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
  },
  accessFetchClient: {
    use: vi.fn(),
  },
}))

const mockUseQuery = vi.mocked(accessClient.useQuery)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type MockQueryResult = {
  data: unknown
  error: null
  isPending: boolean
}

function groupsResult(groups: Array<{ id: string; name: string; is_builtin: boolean }>): MockQueryResult {
  return { data: { resources: groups }, error: null, isPending: false }
}

function membersResult(members: Array<{ id: string; is_enabled: boolean }>): MockQueryResult {
  return { data: { resources: members }, error: null, isPending: false }
}

const emptyResult: MockQueryResult = { data: { resources: [] }, error: null, isPending: false }
const undefinedResult: MockQueryResult = { data: undefined, error: null, isPending: false }

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useActiveAdminCount', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns 0 when no admins group is found', () => {
    // First call: groups query returns no groups
    // Second call: members query returns empty (no group id)
    mockUseQuery.mockReturnValueOnce(emptyResult).mockReturnValueOnce(emptyResult)

    const { result } = renderHook(() => useActiveAdminCount())
    expect(result.current).toBe(0)
  })

  it('returns 0 when groups data is undefined', () => {
    mockUseQuery.mockReturnValueOnce(undefinedResult).mockReturnValueOnce(undefinedResult)

    const { result } = renderHook(() => useActiveAdminCount())
    expect(result.current).toBe(0)
  })

  it('returns the count of enabled members in the admins group', () => {
    mockUseQuery
      .mockReturnValueOnce(groupsResult([{ id: 'admins-id', name: 'admins', is_builtin: true }]))
      .mockReturnValueOnce(
        membersResult([
          { id: 'user-1', is_enabled: true },
          { id: 'user-2', is_enabled: true },
          { id: 'user-3', is_enabled: true },
        ])
      )

    const { result } = renderHook(() => useActiveAdminCount())
    expect(result.current).toBe(3)
  })

  it('filters out disabled members from the count', () => {
    mockUseQuery
      .mockReturnValueOnce(groupsResult([{ id: 'admins-id', name: 'admins', is_builtin: true }]))
      .mockReturnValueOnce(
        membersResult([
          { id: 'user-1', is_enabled: true },
          { id: 'user-2', is_enabled: false },
          { id: 'user-3', is_enabled: true },
          { id: 'user-4', is_enabled: false },
        ])
      )

    const { result } = renderHook(() => useActiveAdminCount())
    expect(result.current).toBe(2)
  })

  it('skips queries when enabled is false', () => {
    mockUseQuery.mockReturnValue(undefinedResult)

    renderHook(() => useActiveAdminCount(false))

    // Both calls should pass enabled: false
    expect(mockUseQuery).toHaveBeenCalledTimes(2)
    // First call (groups): enabled should be false
    expect(mockUseQuery.mock.calls[0][3]).toEqual(expect.objectContaining({ enabled: false }))
    // Second call (members): enabled should also be false (false && anything)
    expect(mockUseQuery.mock.calls[1][3]).toEqual(expect.objectContaining({ enabled: false }))
  })

  it('ignores non-builtin groups named admins', () => {
    mockUseQuery
      .mockReturnValueOnce(groupsResult([{ id: 'custom-id', name: 'admins', is_builtin: false }]))
      .mockReturnValueOnce(emptyResult)

    const { result } = renderHook(() => useActiveAdminCount())
    // No builtin admins group found, so members query gets empty group_id
    expect(result.current).toBe(0)
  })
})
