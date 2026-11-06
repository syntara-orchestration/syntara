import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { accessFetchClient } from '../access/accessClient'

import { useAccessManagementPermissions } from './useAccessManagementPermissions'

vi.mock('../../client', () => ({
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessFetchClient: {
    POST: vi.fn(),
  },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

const CAN_I_COUNT = 11

type CanIBody = {
  action: string
  resource_type: string
  check_any_project?: boolean
}

function mockCanIByBody(allowedFor: (body: CanIBody) => boolean) {
  vi.mocked(accessFetchClient.POST).mockImplementation((_path: string, options: never) => {
    const { body } = options as { body: CanIBody }
    return Promise.resolve({ data: { allowed: allowedFor(body) } } as never)
  })
}

describe('useAccessManagementPermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const allGranted = {
    canReadUsers: true,
    canReadGroups: true,
    canReadProjects: true,
    canReadAssignments: true,
    canReadServiceAccounts: true,
    canReadRoles: true,
    canReadPolicies: true,
    canQueryAuthz: true,
    canReadTokenRevocation: true,
    canAccessPage: true,
    isLoading: false,
  }

  it('defaults to safe-false for all permissions while loading', () => {
    vi.mocked(accessFetchClient.POST).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useAccessManagementPermissions(), { wrapper: createWrapper() })

    expect(result.current).toMatchObject({ canAccessPage: false, isLoading: true })
  })

  it('updates to true when API confirms access', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const { result } = renderHook(() => useAccessManagementPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current).toEqual(allGranted)
    })
  })

  it('updates to false when API denies all access', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: false } })

    const { result } = renderHook(() => useAccessManagementPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current).toEqual({
        canReadUsers: false,
        canReadGroups: false,
        canReadProjects: false,
        canReadAssignments: false,
        canReadServiceAccounts: false,
        canReadRoles: false,
        canReadPolicies: false,
        canQueryAuthz: false,
        canReadTokenRevocation: false,
        canAccessPage: false,
        isLoading: false,
      })
    })
  })

  it('grants canAccessPage for project-admin via check_any_project role-assignment:read', async () => {
    mockCanIByBody(
      (body) =>
        body.check_any_project === true &&
        ((body.resource_type === 'role-assignment' && body.action === 'read') ||
          (body.resource_type === 'project' && body.action === 'read'))
    )

    const { result } = renderHook(() => useAccessManagementPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canReadAssignments).toBe(true)
    expect(result.current.canReadProjects).toBe(true)
    expect(result.current.canAccessPage).toBe(true)
    expect(result.current.canReadRoles).toBe(false)
    expect(result.current.canReadPolicies).toBe(false)
  })

  it('does not grant canAccessPage for project:read alone', async () => {
    mockCanIByBody((body) => body.check_any_project === true && body.resource_type === 'project')

    const { result } = renderHook(() => useAccessManagementPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canReadProjects).toBe(true)
    expect(result.current.canAccessPage).toBe(false)
  })

  it('does not grant canAccessPage for project-scoped service_account:read alone', async () => {
    mockCanIByBody(
      (body) => body.check_any_project === true && body.resource_type === 'service_account' && body.action === 'read'
    )

    const { result } = renderHook(() => useAccessManagementPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current.canReadServiceAccounts).toBe(true)
    expect(result.current.canAccessPage).toBe(false)
  })

  it('handles mixed permissions — canAccessPage true when role-assignment is granted', async () => {
    mockCanIByBody(
      (body) => body.resource_type === 'role-assignment' && body.action === 'read' && body.check_any_project === true
    )

    const { result } = renderHook(() => useAccessManagementPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current).toEqual({
        canReadUsers: false,
        canReadGroups: false,
        canReadProjects: false,
        canReadAssignments: true,
        canReadServiceAccounts: false,
        canReadRoles: false,
        canReadPolicies: false,
        canQueryAuthz: false,
        canReadTokenRevocation: false,
        canAccessPage: true,
        isLoading: false,
      })
    })
  })

  it('calls can_i with check_any_project for project-aware resources', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    renderHook(() => useAccessManagementPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledTimes(CAN_I_COUNT)
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'user' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'role-assignment', check_any_project: true },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'assign', resource_type: 'role-assignment', check_any_project: true },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'service_account', check_any_project: true },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'service_account' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'role' },
    })
    expect(accessFetchClient.POST).toHaveBeenCalledWith('/authz/can_i', {
      body: { action: 'read', resource_type: 'policy' },
    })
  })

  it('deduplicates queries across multiple consumers', async () => {
    vi.mocked(accessFetchClient.POST).mockResolvedValue({ data: { allowed: true } })

    const wrapper = createWrapper()
    renderHook(() => useAccessManagementPermissions(), { wrapper })
    renderHook(() => useAccessManagementPermissions(), { wrapper })

    await waitFor(() => {
      expect(accessFetchClient.POST).toHaveBeenCalledTimes(CAN_I_COUNT)
    })
  })

  it('defaults to false when API call fails (fail-secure)', async () => {
    vi.mocked(accessFetchClient.POST).mockRejectedValue(new Error('network error'))

    const { result } = renderHook(() => useAccessManagementPermissions(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
    expect(result.current).toEqual({
      canReadUsers: false,
      canReadGroups: false,
      canReadProjects: false,
      canReadAssignments: false,
      canReadServiceAccounts: false,
      canReadRoles: false,
      canReadPolicies: false,
      canQueryAuthz: false,
      canReadTokenRevocation: false,
      canAccessPage: false,
      isLoading: false,
    })
  })
})
