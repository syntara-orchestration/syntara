import { renderHook } from '@testing-library/react'
import { act } from 'react'
import { describe, expect, it } from 'vitest'

import type { ApprovalWithDetails } from './Approvals'
import { useApprovalSelection } from './useApprovalSelection'

describe('useApprovalSelection', () => {
  const mockPendingApproval: ApprovalWithDetails = {
    id: 'approval-1',
    project_id: 'project-1',
    execution_id: 'exec-1',
    approval_node_id: 'node-1',
    name: 'Test Approval 1',
    status: 'pending',
    created_at: '2024-01-01T00:00:00Z',
    next_step_approved: { id: 'step-1', name: 'Next Step', type: 'task' },
    workflow_context: {
      workflow_id: 'wf-1',
      workflow_name: 'Test Workflow 1',
      inputs: {},
    },
    approvalName: 'Test Approval 1',
    workflowName: 'Test Workflow 1',
    workflowId: 'wf-1',
  }

  const mockApprovedApproval: ApprovalWithDetails = {
    id: 'approval-2',
    project_id: 'project-1',
    execution_id: 'exec-2',
    approval_node_id: 'node-2',
    name: 'Test Approval 2',
    status: 'approved',
    created_at: '2024-01-01T00:00:00Z',
    decided_at: '2024-01-01T01:00:00Z',
    next_step_approved: { id: 'step-2', name: 'Next Step', type: 'task' },
    workflow_context: {
      workflow_id: 'wf-2',
      workflow_name: 'Test Workflow 2',
      inputs: {},
    },
    approvalName: 'Test Approval 2',
    workflowName: 'Test Workflow 2',
    workflowId: 'wf-2',
  }

  const mockRejectedApproval: ApprovalWithDetails = {
    id: 'approval-3',
    project_id: 'project-1',
    execution_id: 'exec-3',
    approval_node_id: 'node-3',
    name: 'Test Approval 3',
    status: 'rejected',
    created_at: '2024-01-01T00:00:00Z',
    decided_at: '2024-01-01T01:00:00Z',
    next_step_approved: { id: 'step-3', name: 'Next Step', type: 'task' },
    workflow_context: {
      workflow_id: 'wf-3',
      workflow_name: 'Test Workflow 3',
      inputs: {},
    },
    approvalName: 'Test Approval 3',
    workflowName: 'Test Workflow 3',
    workflowId: 'wf-3',
  }

  const mockApprovals = [mockPendingApproval, mockApprovedApproval, mockRejectedApproval]
  const mockFilters = {}
  const mockSortParam = '-created_at'
  const mockApprovalPermissions = new Map([
    ['approval-1', true],
    ['approval-2', true],
    ['approval-3', true],
  ])
  const mockIsLoadingPermissions = false
  const mockSelectableApprovalIds = new Set(['approval-1']) // Only pending approval is selectable

  it('initializes with empty selection', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: mockSelectableApprovalIds,
      })
    )

    expect(result.current.selectedApprovalIds.size).toBe(0)
  })

  it('identifies pending approvals', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: mockSelectableApprovalIds,
      })
    )

    expect(result.current.pendingApprovals).toHaveLength(1)
    expect(result.current.pendingApprovals[0]?.id).toBe('approval-1')
  })

  it('selects a single pending approval', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: mockSelectableApprovalIds,
      })
    )

    act(() => {
      result.current.handleSelectRow(mockPendingApproval, true)
    })

    expect(result.current.selectedApprovalIds.has('approval-1')).toBe(true)
    expect(result.current.selectedApprovalIds.size).toBe(1)
  })

  it('deselects a previously selected approval', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: mockSelectableApprovalIds,
      })
    )

    act(() => {
      result.current.handleSelectRow(mockPendingApproval, true)
    })

    expect(result.current.selectedApprovalIds.has('approval-1')).toBe(true)

    act(() => {
      result.current.handleSelectRow(mockPendingApproval, false)
    })

    expect(result.current.selectedApprovalIds.has('approval-1')).toBe(false)
    expect(result.current.selectedApprovalIds.size).toBe(0)
  })

  it('ignores selection of non-pending approvals', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: mockSelectableApprovalIds,
      })
    )

    act(() => {
      result.current.handleSelectRow(mockApprovedApproval, true)
    })

    expect(result.current.selectedApprovalIds.has('approval-2')).toBe(false)
    expect(result.current.selectedApprovalIds.size).toBe(0)
  })

  it('selects all pending approvals', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: mockSelectableApprovalIds,
      })
    )

    act(() => {
      result.current.handleSelectAll(true)
    })

    expect(result.current.selectedApprovalIds.has('approval-1')).toBe(true)
    expect(result.current.selectedApprovalIds.has('approval-2')).toBe(false) // approved, not selected
    expect(result.current.selectedApprovalIds.has('approval-3')).toBe(false) // rejected, not selected
    expect(result.current.selectedApprovalIds.size).toBe(1)
  })

  it('deselects all pending approvals', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: mockSelectableApprovalIds,
      })
    )

    act(() => {
      result.current.handleSelectAll(true)
    })

    expect(result.current.selectedApprovalIds.size).toBe(1)

    act(() => {
      result.current.handleSelectAll(false)
    })

    expect(result.current.selectedApprovalIds.size).toBe(0)
  })

  it('reports all pending selected when all are selected', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: mockSelectableApprovalIds,
      })
    )

    expect(result.current.allPendingSelected).toBe(false)

    act(() => {
      result.current.handleSelectAll(true)
    })

    expect(result.current.allPendingSelected).toBe(true)
  })

  it('clears all selections', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: mockSelectableApprovalIds,
      })
    )

    act(() => {
      result.current.handleSelectRow(mockPendingApproval, true)
    })

    expect(result.current.selectedApprovalIds.size).toBe(1)

    act(() => {
      result.current.clearSelectedApprovalIds()
    })

    expect(result.current.selectedApprovalIds.size).toBe(0)
  })

  it('preserves off-page selections when approvals change', () => {
    const { result, rerender } = renderHook(
      ({ enrichedApprovals }) =>
        useApprovalSelection(enrichedApprovals, enrichedApprovals, {
          filters: mockFilters,
          sortParam: mockSortParam,
          approvalPermissions: mockApprovalPermissions,
          isLoadingPermissions: mockIsLoadingPermissions,
          selectableApprovalIds: mockSelectableApprovalIds,
        }),
      {
        initialProps: { enrichedApprovals: mockApprovals },
      }
    )

    // Select the pending approval
    act(() => {
      result.current.handleSelectRow(mockPendingApproval, true)
    })

    expect(result.current.selectedApprovalIds.has('approval-1')).toBe(true)

    // Simulate page change - different approvals that don't include approval-1
    const newPageApprovals = [mockApprovedApproval, mockRejectedApproval]

    rerender({ enrichedApprovals: newPageApprovals })

    // Selection should be preserved even though approval-1 is not on this page
    expect(result.current.selectedApprovalIds.has('approval-1')).toBe(true)
  })

  it('removes selections when approval is no longer pending', () => {
    const { result, rerender } = renderHook(
      ({ enrichedApprovals }) =>
        useApprovalSelection(enrichedApprovals, enrichedApprovals, {
          filters: mockFilters,
          sortParam: mockSortParam,
          approvalPermissions: mockApprovalPermissions,
          isLoadingPermissions: mockIsLoadingPermissions,
          selectableApprovalIds: mockSelectableApprovalIds,
        }),
      {
        initialProps: { enrichedApprovals: mockApprovals },
      }
    )

    act(() => {
      result.current.handleSelectRow(mockPendingApproval, true)
    })

    expect(result.current.selectedApprovalIds.has('approval-1')).toBe(true)

    // Simulate the approval being approved
    const updatedApproval = { ...mockPendingApproval, status: 'approved' as const }
    const updatedApprovals = [updatedApproval, mockApprovedApproval, mockRejectedApproval]

    rerender({ enrichedApprovals: updatedApprovals })

    // Selection should be cleared because the approval is no longer pending
    expect(result.current.selectedApprovalIds.has('approval-1')).toBe(false)
  })

  it('clears selections when filters change', () => {
    const { result, rerender } = renderHook(
      ({ filters }) =>
        useApprovalSelection(mockApprovals, mockApprovals, {
          filters,
          sortParam: mockSortParam,
          approvalPermissions: mockApprovalPermissions,
          isLoadingPermissions: mockIsLoadingPermissions,
          selectableApprovalIds: mockSelectableApprovalIds,
        }),
      {
        initialProps: { filters: mockFilters },
      }
    )

    act(() => {
      result.current.handleSelectRow(mockPendingApproval, true)
    })

    expect(result.current.selectedApprovalIds.size).toBe(1)

    // Change filters
    const newFilters = { status: 'pending' }
    rerender({ filters: newFilters })

    expect(result.current.selectedApprovalIds.size).toBe(0)
  })

  it('clears selections when sort changes', () => {
    const { result, rerender } = renderHook(
      ({ sortParam }) =>
        useApprovalSelection(mockApprovals, mockApprovals, {
          filters: mockFilters,
          sortParam,
          approvalPermissions: mockApprovalPermissions,
          isLoadingPermissions: mockIsLoadingPermissions,
          selectableApprovalIds: mockSelectableApprovalIds,
        }),
      {
        initialProps: { sortParam: '-created_at' },
      }
    )

    act(() => {
      result.current.handleSelectRow(mockPendingApproval, true)
    })

    expect(result.current.selectedApprovalIds.size).toBe(1)

    // Change sort
    rerender({ sortParam: 'name' })

    expect(result.current.selectedApprovalIds.size).toBe(0)
  })

  it('handles empty approvals list', () => {
    const { result } = renderHook(() =>
      useApprovalSelection([], [], {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: new Map(),
        isLoadingPermissions: mockIsLoadingPermissions,
        selectableApprovalIds: new Set(),
      })
    )

    expect(result.current.selectedApprovalIds.size).toBe(0)
    expect(result.current.pendingApprovals).toHaveLength(0)
    expect(result.current.allPendingSelected).toBe(false)
  })

  it('select all only selects approvals in selectable set', () => {
    const pendingApproval1 = { ...mockPendingApproval, id: 'approval-1' }
    const pendingApproval2 = { ...mockPendingApproval, id: 'approval-2' }
    const approvals = [pendingApproval1, pendingApproval2]

    const permissionMap = new Map([
      ['approval-1', true],
      ['approval-2', true],
    ])

    // Only approval-1 is selectable (approval-2 is disabled for some reason, e.g. not on approver list)
    const selectableSet = new Set(['approval-1'])

    const { result } = renderHook(() =>
      useApprovalSelection(approvals, approvals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: permissionMap,
        isLoadingPermissions: false,
        selectableApprovalIds: selectableSet,
      })
    )

    act(() => {
      result.current.handleSelectAll(true)
    })

    // Should only select approval-1 (pending + in selectable set)
    expect(result.current.selectedApprovalIds.size).toBe(1)
    expect(result.current.selectedApprovalIds.has('approval-1')).toBe(true)
    expect(result.current.selectedApprovalIds.has('approval-2')).toBe(false)
  })

  it('select all is disabled when permissions are loading', () => {
    const { result } = renderHook(() =>
      useApprovalSelection(mockApprovals, mockApprovals, {
        filters: mockFilters,
        sortParam: mockSortParam,
        approvalPermissions: mockApprovalPermissions,
        isLoadingPermissions: true,
        selectableApprovalIds: new Set(), // Empty when loading
      })
    )

    act(() => {
      result.current.handleSelectAll(true)
    })

    // Should not select anything while loading
    expect(result.current.selectedApprovalIds.size).toBe(0)
  })
})
