import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import type { ApprovalWithDetails } from './Approvals'
import { useApprovalsData } from './useApprovalsData'

// Mock the clients
vi.mock('../../client', () => ({
  approvalsClient: {
    useQuery: vi.fn(),
  },
  authMiddleware: { onRequest: vi.fn() },
  interfaceTagMiddleware: { onRequest: vi.fn() },
}))

vi.mock('../access/accessClient', () => ({
  accessClient: {
    useQuery: vi.fn(),
  },
}))

describe('useApprovalsData', () => {
  let queryClient: QueryClient

  const mockApproval1 = {
    id: 'approval-1',
    name: 'Test Approval 1',
    status: 'pending',
    created_at: '2024-01-01T00:00:00Z',
    workflow_context: {
      workflow_id: 'wf-1',
      workflow_version: 3,
      workflow_name: 'Test Workflow 1',
      inputs: {},
    },
  }

  const mockApproval2 = {
    id: 'approval-2',
    name: 'Test Approval 2',
    status: 'approved',
    created_at: '2024-01-02T00:00:00Z',
    decided_at: '2024-01-02T01:00:00Z',
    workflow_context: {
      workflow_id: 'wf-2',
      workflow_version: 5,
      workflow_name: 'Test Workflow 2',
      inputs: {},
    },
  }

  const mockProjects = [
    { id: 'project-1', name: 'Project 1' },
    { id: 'project-2', name: 'Project 2' },
  ]

  const createWrapper = () => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })

    return ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { approvalsClient } = await import('../../client')
    const { accessClient } = await import('../access/accessClient')

    // Default mock implementations
    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })

    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: { resources: [] },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })
  })

  it('enriches approvals with approval name, workflow name, and workflow ID', async () => {
    const { approvalsClient } = await import('../../client')

    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: { resources: [mockApproval1, mockApproval2] },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useApprovalsData({
          projectSelectorReady: true,
          isAllProjects: true,
          stableProjectId: null,
          queryParams: {},
          projects: mockProjects,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.enrichedApprovals).toHaveLength(2)
    })

    const enriched = result.current.enrichedApprovals as ApprovalWithDetails[]
    expect(enriched[0]?.approvalName).toBe('Test Approval 1')
    expect(enriched[0]?.workflowName).toBe('Test Workflow 1')
    expect(enriched[0]?.workflowId).toBe('wf-1')
    expect(enriched[0]?.workflowVersion).toBe(3)
  })

  it('uses approval ID as fallback for approvalName when name is missing', async () => {
    const approvalWithoutName = {
      id: 'approval-3',
      status: 'pending',
      created_at: '2024-01-03T00:00:00Z',
      workflow_context: {
        workflow_id: 'wf-3',
        workflow_version: 1,
        workflow_name: 'Test Workflow 3',
        inputs: {},
      },
    }

    const { approvalsClient } = await import('../../client')

    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: { resources: [approvalWithoutName] },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useApprovalsData({
          projectSelectorReady: true,
          isAllProjects: true,
          stableProjectId: null,
          queryParams: {},
          projects: mockProjects,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.enrichedApprovals).toHaveLength(1)
    })

    const enriched = result.current.enrichedApprovals as ApprovalWithDetails[]
    expect(enriched[0]?.approvalName).toBe('approval-3')
  })

  it('uses "Unknown" as fallback for workflowName when missing', async () => {
    const approvalWithoutWorkflow = {
      id: 'approval-4',
      name: 'Test Approval 4',
      status: 'pending',
      created_at: '2024-01-04T00:00:00Z',
    }

    const { approvalsClient } = await import('../../client')

    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: { resources: [approvalWithoutWorkflow] },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useApprovalsData({
          projectSelectorReady: true,
          isAllProjects: true,
          stableProjectId: null,
          queryParams: {},
          projects: mockProjects,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.enrichedApprovals).toHaveLength(1)
    })

    const enriched = result.current.enrichedApprovals as ApprovalWithDetails[]
    expect(enriched[0]?.workflowName).toBe('Unknown')
  })

  it('preserves API order in sortedApprovals', async () => {
    const { approvalsClient } = await import('../../client')

    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: { resources: [mockApproval2, mockApproval1] },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useApprovalsData({
          projectSelectorReady: true,
          isAllProjects: true,
          stableProjectId: null,
          queryParams: { sort: '-created_at' },
          projects: mockProjects,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.sortedApprovals).toHaveLength(2)
    })

    const sorted = result.current.sortedApprovals as ApprovalWithDetails[]
    expect(sorted[0]?.id).toBe('approval-2')
    expect(sorted[1]?.id).toBe('approval-1')
    expect(sorted).toEqual(result.current.enrichedApprovals)
  })

  it('groups approvals by project when isAllProjects is true', async () => {
    const approvalWithProject1 = { ...mockApproval1, project_id: 'project-1' }
    const approvalWithProject2 = { ...mockApproval2, project_id: 'project-2' }

    const { approvalsClient } = await import('../../client')

    vi.mocked(approvalsClient.useQuery).mockReturnValue({
      data: { resources: [approvalWithProject1, approvalWithProject2] },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useApprovalsData({
          projectSelectorReady: true,
          isAllProjects: true,
          stableProjectId: null,
          queryParams: {},
          projects: mockProjects,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.groupedApprovals).not.toBeNull()
    })

    const grouped = result.current.groupedApprovals!
    expect(grouped.size).toBe(2)
    expect(grouped.get('project-1')?.project?.name).toBe('Project 1')
    expect(grouped.get('project-1')?.approvals).toHaveLength(1)
    expect(grouped.get('project-2')?.project?.name).toBe('Project 2')
    expect(grouped.get('project-2')?.approvals).toHaveLength(1)
  })

  it('does not group approvals when isAllProjects is false', async () => {
    const { accessClient } = await import('../access/accessClient')

    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: { resources: [mockApproval1] },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useApprovalsData({
          projectSelectorReady: true,
          isAllProjects: false,
          stableProjectId: 'project-1',
          queryParams: {},
          projects: mockProjects,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.groupedApprovals).toBeNull()
    })
  })

  it('uses accessClient query when a specific project is selected', async () => {
    const { accessClient } = await import('../access/accessClient')

    vi.mocked(accessClient.useQuery).mockReturnValue({
      data: { resources: [mockApproval1] },
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
    })

    const { result } = renderHook(
      () =>
        useApprovalsData({
          projectSelectorReady: true,
          isAllProjects: false,
          stableProjectId: 'project-1',
          queryParams: {},
          projects: mockProjects,
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.enrichedApprovals).toHaveLength(1)
    })

    expect(accessClient.useQuery).toHaveBeenCalled()
  })

  it('returns empty arrays when projectSelectorReady is false', () => {
    const { result } = renderHook(
      () =>
        useApprovalsData({
          projectSelectorReady: false,
          isAllProjects: true,
          stableProjectId: null,
          queryParams: {},
          projects: mockProjects,
        }),
      { wrapper: createWrapper() }
    )

    expect(result.current.enrichedApprovals).toHaveLength(0)
    expect(result.current.sortedApprovals).toHaveLength(0)
  })
})
