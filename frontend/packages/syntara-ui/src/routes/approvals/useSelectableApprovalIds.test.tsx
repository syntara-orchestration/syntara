import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { usersClient } from '../../client'
import { useAuthStore } from '../../stores/useAuthStore'

import type { ApprovalWithDetails } from './Approvals'
import { useSelectableApprovalIds } from './useSelectableApprovalIds'

vi.mock('../../client', () => ({
  usersClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../../stores/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}))

describe('useSelectableApprovalIds', () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  function TestWrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }

  const mockApproval = (
    id: string,
    status: string,
    approverUsers?: { id: string; username: string }[],
    approverGroups?: { id: string; name: string }[]
  ): ApprovalWithDetails =>
    ({
      id,
      status,
      approver_users: approverUsers,
      approver_groups: approverGroups,
    }) as ApprovalWithDetails

  it('returns empty set when loading permissions', () => {
    vi.mocked(useAuthStore).mockReturnValue('alice')
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isLoading: false,
    })

    const approvals = [mockApproval('1', 'pending')]
    const approvalPermissions = new Map([['1', true]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, true), {
      wrapper: TestWrapper,
    })

    expect(result.current.size).toBe(0)
  })

  it('returns empty set when loading user groups', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'alice', userId: 'user-1' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
    })

    const approvals = [mockApproval('1', 'pending')]
    const approvalPermissions = new Map([['1', true]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.size).toBe(0)
  })

  it('includes approval when user has RBAC permission and no approvers configured', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'alice', userId: 'user-1' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isLoading: false,
    })

    const approvals = [mockApproval('1', 'pending')]
    const approvalPermissions = new Map([['1', true]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.has('1')).toBe(true)
  })

  it('includes approval when user is in approver_users', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'alice', userId: 'user-1' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isLoading: false,
    })

    const approvals = [mockApproval('1', 'pending', [{ id: '1', username: 'alice' }])]
    const approvalPermissions = new Map([['1', true]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.has('1')).toBe(true)
  })

  it('excludes approval when user is not in approver_users', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'charlie', userId: 'user-3' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isLoading: false,
    })

    const approvals = [mockApproval('1', 'pending', [{ id: '1', username: 'alice' }])]
    const approvalPermissions = new Map([['1', true]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.has('1')).toBe(false)
  })

  it('includes approval when user is in approver_groups', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'alice', userId: 'user-1' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: {
        resources: [{ id: 'group-1', name: 'Admins' }],
      },
      isLoading: false,
    })

    const approvals = [mockApproval('1', 'pending', undefined, [{ id: 'group-1', name: 'Admins' }])]
    const approvalPermissions = new Map([['1', true]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.has('1')).toBe(true)
  })

  it('excludes approval when user is not in approver_groups', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'alice', userId: 'user-1' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: {
        resources: [{ id: 'group-2', name: 'Other' }],
      },
      isLoading: false,
    })

    const approvals = [mockApproval('1', 'pending', undefined, [{ id: 'group-1', name: 'Admins' }])]
    const approvalPermissions = new Map([['1', true]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.has('1')).toBe(false)
  })

  it('excludes approval when status is not pending', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'alice', userId: 'user-1' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isLoading: false,
    })

    const approvals = [mockApproval('1', 'approved')]
    const approvalPermissions = new Map([['1', true]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.has('1')).toBe(false)
  })

  it('excludes approval when user lacks RBAC permission', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'alice', userId: 'user-1' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isLoading: false,
    })

    const approvals = [mockApproval('1', 'pending')]
    const approvalPermissions = new Map([['1', false]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.has('1')).toBe(false)
  })

  it('filters out user groups with missing id or name', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'alice', userId: 'user-1' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: {
        resources: [
          { id: 'group-1', name: 'Valid Group' },
          { id: '', name: 'Missing ID' },
          { id: 'group-3', name: '' },
          { name: 'Missing Both' },
        ],
      },
      isLoading: false,
    })

    const approvals = [mockApproval('1', 'pending', undefined, [{ id: 'group-1', name: 'Valid Group' }])]
    const approvalPermissions = new Map([['1', true]])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.has('1')).toBe(true)
  })

  it('handles multiple approvals with mixed selectability', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: 'alice', userId: 'user-1' }
      return selector(state as never)
    })
    vi.mocked(usersClient.useQuery).mockReturnValue({
      data: {
        resources: [{ id: 'group-1', name: 'Admins' }],
      },
      isLoading: false,
    })

    const approvals = [
      mockApproval('1', 'pending'), // selectable - no approvers
      mockApproval('2', 'pending', [{ id: '2', username: 'bob' }]), // not selectable - not in approver_users
      mockApproval('3', 'pending', undefined, [{ id: 'group-1', name: 'Admins' }]), // selectable - in approver_groups
      mockApproval('4', 'approved'), // not selectable - not pending
    ]
    const approvalPermissions = new Map([
      ['1', true],
      ['2', true],
      ['3', true],
      ['4', true],
    ])

    const { result } = renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(result.current.has('1')).toBe(true)
    expect(result.current.has('2')).toBe(false)
    expect(result.current.has('3')).toBe(true)
    expect(result.current.has('4')).toBe(false)
  })

  it('skips query when currentUserId is null', () => {
    vi.mocked(useAuthStore).mockImplementation((selector) => {
      const state = { username: null, userId: null }
      return selector(state as never)
    })

    const mockUseQuery = vi.fn().mockReturnValue({
      data: undefined,
      isLoading: false,
    })
    vi.mocked(usersClient.useQuery).mockImplementation(mockUseQuery as never)

    const approvals = [mockApproval('1', 'pending')]
    const approvalPermissions = new Map([['1', true]])

    renderHook(() => useSelectableApprovalIds(approvals, approvalPermissions, false), {
      wrapper: TestWrapper,
    })

    expect(mockUseQuery).toHaveBeenCalledWith('get', '/users/{user_id}/groups', {
      params: { path: { user_id: '' } },
      enabled: false,
    })
  })
})
