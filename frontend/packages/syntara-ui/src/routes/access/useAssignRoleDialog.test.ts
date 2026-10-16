import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

import { accessClient } from './accessClient'
import type { AssignRoleFormData } from './assignRoleSchema'
import { useAssignRoleDialog } from './useAssignRoleDialog'
import { useAssignRoleFormQueries } from './useAssignRoleFormQueries'

const mockShowSuccess = vi.fn()
const mockOnClose = vi.fn()
const mockOnSuccess = vi.fn()
const mockCreateSystemAssignment = vi.fn()
const mockCreateProjectAssignment = vi.fn()
vi.mock('../../providers/alerts', () => ({
  useAlerts: () => ({ showSuccess: mockShowSuccess, showAlert: vi.fn() }),
}))

vi.mock('./accessClient', () => ({
  accessClient: {
    useMutation: vi.fn(),
  },
}))

vi.mock('./useAssignRoleFormQueries', () => ({
  useAssignRoleFormQueries: vi.fn(),
}))

function createQueryWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

function mockFormQueries(overrides?: Partial<ReturnType<typeof useAssignRoleFormQueries>>) {
  const base = {
    principalType: RolePrincipalType.USER,
    isProjectScoped: false,
    selectedProjectId: '',
    projectOptions: [],
    userOptions: [{ value: 'user-1', label: 'alice' }],
    groupOptions: [],
    serviceAccountOptions: [],
    roleOptions: [{ value: 'editor', label: 'editor' }],
    isProjectsLoading: false,
    setUserSearchTerm: vi.fn(),
    usersQuery: { data: { next: null }, isFetching: false },
    setGroupSearchTerm: vi.fn(),
    groupsQuery: { data: { next: null }, isFetching: false },
    setSaSearchTerm: vi.fn(),
    serviceAccountsQuery: { data: { next: null }, isFetching: false },
    setRoleSearchTerm: vi.fn(),
    activeRolesQuery: { data: { next: null }, isFetching: false },
    isAssignmentsLoading: false,
    isAssignmentsError: false,
  }
  vi.mocked(useAssignRoleFormQueries).mockReturnValue({ ...base, ...overrides } as never)
}

const systemSubmitData: AssignRoleFormData = {
  principalType: RolePrincipalType.USER,
  scope: 'system',
  userId: 'user-1',
  groupId: '',
  serviceAccountId: '',
  projectId: '',
  roleName: 'editor',
}

describe('useAssignRoleDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFormQueries()
    vi.mocked(accessClient.useMutation).mockImplementation((_method, path) => {
      if (path === '/role_assignments') {
        return { mutate: mockCreateSystemAssignment, isPending: false } as never
      }
      return { mutate: mockCreateProjectAssignment, isPending: false } as never
    })
  })

  it('clears principal ids when principal type changes', () => {
    const { result } = renderHook(() => useAssignRoleDialog({ onClose: mockOnClose, onSuccess: mockOnSuccess }), {
      wrapper: createQueryWrapper(),
    })

    const { form, onPrincipalTypeChange } = result.current.formBodyProps
    act(() => {
      form.setValue('userId', 'user-1')
      form.setValue('groupId', 'group-1')
      form.setValue('serviceAccountId', 'sa-1')
      onPrincipalTypeChange(RolePrincipalType.SERVICE_ACCOUNT)
    })

    expect(form.getValues('userId')).toBe('')
    expect(form.getValues('groupId')).toBe('')
    expect(form.getValues('serviceAccountId')).toBe('')
    expect(form.getValues('scope')).toBe('project')
  })

  it('clears role and project when scope changes away from project', () => {
    const { result } = renderHook(() => useAssignRoleDialog({ onClose: mockOnClose, onSuccess: mockOnSuccess }), {
      wrapper: createQueryWrapper(),
    })

    const { form, onScopeChange } = result.current.formBodyProps
    act(() => {
      form.setValue('projectId', 'proj-1')
      form.setValue('roleName', 'admin')
      onScopeChange('system')
    })

    expect(form.getValues('projectId')).toBe('')
    expect(form.getValues('roleName')).toBe('')
  })

  it('clears role when project changes', () => {
    const { result } = renderHook(() => useAssignRoleDialog({ onClose: mockOnClose, onSuccess: mockOnSuccess }), {
      wrapper: createQueryWrapper(),
    })

    const { form, onProjectChange } = result.current.formBodyProps
    act(() => {
      form.setValue('roleName', 'admin')
      onProjectChange('proj-1')
    })

    expect(form.getValues('roleName')).toBe('')
  })

  it('uses system role assignment mutation for system scope', () => {
    const { result } = renderHook(() => useAssignRoleDialog({ onClose: mockOnClose, onSuccess: mockOnSuccess }), {
      wrapper: createQueryWrapper(),
    })

    act(() => {
      result.current.onSubmit(systemSubmitData)
    })

    expect(mockCreateSystemAssignment).toHaveBeenCalledOnce()
    expect(mockCreateProjectAssignment).not.toHaveBeenCalled()
  })

  it('uses project role assignment mutation for project scope', () => {
    const { result } = renderHook(() => useAssignRoleDialog({ onClose: mockOnClose, onSuccess: mockOnSuccess }), {
      wrapper: createQueryWrapper(),
    })

    act(() => {
      result.current.onSubmit({
        ...systemSubmitData,
        scope: 'project',
        projectId: 'proj-1',
      })
    })

    expect(mockCreateProjectAssignment).toHaveBeenCalledOnce()
    expect(mockCreateSystemAssignment).not.toHaveBeenCalled()
    const [request] = mockCreateProjectAssignment.mock.calls[0] as [{ params: { path: { project_id: string } } }]
    expect(request.params.path.project_id).toBe('proj-1')
  })

  it('shows success, closes, and calls onSuccess after mutation succeeds', () => {
    mockCreateSystemAssignment.mockImplementation((_req, { onSuccess }: { onSuccess: () => void }) => {
      onSuccess()
    })

    const { result } = renderHook(() => useAssignRoleDialog({ onClose: mockOnClose, onSuccess: mockOnSuccess }), {
      wrapper: createQueryWrapper(),
    })

    act(() => {
      result.current.onSubmit(systemSubmitData)
    })

    expect(mockShowSuccess).toHaveBeenCalledWith(expect.objectContaining({ title: 'Assignment added' }))
    expect(mockOnClose).toHaveBeenCalled()
    expect(mockOnSuccess).toHaveBeenCalled()
  })

  it('does not complete the dialog flow when mutation fails', () => {
    mockCreateSystemAssignment.mockImplementation((_req, { onError }: { onError: (err: Error) => void }) => {
      onError(new Error('failed'))
    })

    const { result } = renderHook(() => useAssignRoleDialog({ onClose: mockOnClose, onSuccess: mockOnSuccess }), {
      wrapper: createQueryWrapper(),
    })

    act(() => {
      result.current.onSubmit(systemSubmitData)
    })

    expect(mockOnSuccess).not.toHaveBeenCalled()
    expect(mockShowSuccess).not.toHaveBeenCalled()
  })
})
