import type { Approval } from '@syntara/contracts'
import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useApprovalNavigation } from './useApprovalNavigation'

const mockApprovals: Approval[] = [
  {
    id: 'approval-1',
    project_id: 'test-project-1',
    name: 'Approval 1',
    status: 'pending',
    approval_node_id: 'node-1',
    execution_id: 'exec-1',
    created_at: '2024-01-01T00:00:00Z',
    next_step_approved: {
      id: 'approved-step',
      name: 'Approved Step',
      type: 'script_python',
    },
    workflow_context: {
      workflow_name: 'Test Workflow',
      workflow_id: 'wfv-1',
      inputs: {},
    },
  },
  {
    id: 'approval-2',
    project_id: 'test-project-1',
    name: 'Approval 2',
    status: 'pending',
    approval_node_id: 'node-2',
    execution_id: 'exec-1',
    created_at: '2024-01-01T00:01:00Z',
    next_step_approved: {
      id: 'approved-step',
      name: 'Approved Step',
      type: 'script_python',
    },
    workflow_context: {
      workflow_name: 'Test Workflow',
      workflow_id: 'wfv-1',
      inputs: {},
    },
  },
  {
    id: 'approval-3',
    project_id: 'test-project-1',
    name: 'Approval 3',
    status: 'pending',
    approval_node_id: 'node-3',
    execution_id: 'exec-1',
    created_at: '2024-01-01T00:02:00Z',
    next_step_approved: {
      id: 'approved-step',
      name: 'Approved Step',
      type: 'script_python',
    },
    workflow_context: {
      workflow_name: 'Test Workflow',
      workflow_id: 'wfv-1',
      inputs: {},
    },
  },
]

describe('useApprovalNavigation', () => {
  it('returns correct navigation state for first approval', () => {
    const { result } = renderHook(() => useApprovalNavigation(0, vi.fn(), mockApprovals))

    expect(result.current.current).toBe(mockApprovals[0])
    expect(result.current.currentIndex).toBe(0)
    expect(result.current.total).toBe(3)
    expect(result.current.hasPrev).toBe(false)
    expect(result.current.hasNext).toBe(true)
  })

  it('returns correct navigation state for middle approval', () => {
    const { result } = renderHook(() => useApprovalNavigation(1, vi.fn(), mockApprovals))

    expect(result.current.current).toBe(mockApprovals[1])
    expect(result.current.currentIndex).toBe(1)
    expect(result.current.total).toBe(3)
    expect(result.current.hasPrev).toBe(true)
    expect(result.current.hasNext).toBe(true)
  })

  it('returns correct navigation state for last approval', () => {
    const { result } = renderHook(() => useApprovalNavigation(2, vi.fn(), mockApprovals))

    expect(result.current.current).toBe(mockApprovals[2])
    expect(result.current.currentIndex).toBe(2)
    expect(result.current.total).toBe(3)
    expect(result.current.hasPrev).toBe(true)
    expect(result.current.hasNext).toBe(false)
  })

  it('returns null current when approvals array is empty', () => {
    const { result } = renderHook(() => useApprovalNavigation(0, vi.fn(), []))

    expect(result.current.current).toBeNull()
    expect(result.current.currentIndex).toBe(0)
    expect(result.current.total).toBe(0)
    expect(result.current.hasPrev).toBe(false)
    expect(result.current.hasNext).toBe(false)
  })

  it('returns null current when currentIndex is out of bounds', () => {
    const { result } = renderHook(() => useApprovalNavigation(10, vi.fn(), mockApprovals))

    expect(result.current.current).toBeNull()
    expect(result.current.currentIndex).toBe(10)
    expect(result.current.total).toBe(3)
  })

  it('calls onNavigate with decremented index when navigatePrev is called', () => {
    const onNavigate = vi.fn()
    const { result } = renderHook(() => useApprovalNavigation(1, onNavigate, mockApprovals))

    result.current.navigatePrev()

    expect(onNavigate).toHaveBeenCalledTimes(1)
    expect(onNavigate).toHaveBeenCalledWith(0)
  })

  it('calls onNavigate with incremented index when navigateNext is called', () => {
    const onNavigate = vi.fn()
    const { result } = renderHook(() => useApprovalNavigation(1, onNavigate, mockApprovals))

    result.current.navigateNext()

    expect(onNavigate).toHaveBeenCalledTimes(1)
    expect(onNavigate).toHaveBeenCalledWith(2)
  })

  it('does not call onNavigate when navigatePrev is called at first index', () => {
    const onNavigate = vi.fn()
    const { result } = renderHook(() => useApprovalNavigation(0, onNavigate, mockApprovals))

    result.current.navigatePrev()

    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('does not call onNavigate when navigateNext is called at last index', () => {
    const onNavigate = vi.fn()
    const { result } = renderHook(() => useApprovalNavigation(2, onNavigate, mockApprovals))

    result.current.navigateNext()

    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('handles single approval correctly', () => {
    const singleApproval = [mockApprovals[0]]
    const { result } = renderHook(() => useApprovalNavigation(0, vi.fn(), singleApproval))

    expect(result.current.current).toBe(singleApproval[0])
    expect(result.current.total).toBe(1)
    expect(result.current.hasPrev).toBe(false)
    expect(result.current.hasNext).toBe(false)
  })

  it('handles undefined approvals array', () => {
    const { result } = renderHook(() => useApprovalNavigation(0, vi.fn(), undefined))

    expect(result.current.current).toBeNull()
    expect(result.current.total).toBe(0)
    expect(result.current.hasPrev).toBe(false)
    expect(result.current.hasNext).toBe(false)
  })

  it('memoizes navigation callbacks', () => {
    const onNavigate = vi.fn()
    const { result, rerender } = renderHook(({ index }) => useApprovalNavigation(index, onNavigate, mockApprovals), {
      initialProps: { index: 0 },
    })

    const firstNavigatePrev = result.current.navigatePrev
    const firstNavigateNext = result.current.navigateNext

    rerender({ index: 0 })

    // Callbacks should be stable if dependencies haven't changed
    expect(result.current.navigatePrev).toBe(firstNavigatePrev)
    expect(result.current.navigateNext).toBe(firstNavigateNext)
  })
})
