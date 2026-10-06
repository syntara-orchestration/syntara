import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TASKS_TAB_APPROVALS, TASKS_TAB_FORM_RESPONSES, useTasksTabAccess } from './useTasksTabAccess'

const mockUseApprovalPermissions = vi.hoisted(() => vi.fn())
const mockUseFormPromptPermissions = vi.hoisted(() => vi.fn())

vi.mock('../approvals/useApprovalPermissions', () => ({
  useApprovalPermissions: mockUseApprovalPermissions,
}))

vi.mock('../executions/hooks/useFormPromptPermissions', () => ({
  useFormPromptPermissions: mockUseFormPromptPermissions,
}))

describe('useTasksTabAccess', () => {
  beforeEach(() => {
    mockUseApprovalPermissions.mockReturnValue({ canRead: true, isChecking: false, isError: false })
    mockUseFormPromptPermissions.mockReturnValue({ canRead: true, isChecking: false, isError: false })
  })

  it('exposes both tabs when the user can read approvals and form prompts', () => {
    const { result } = renderHook(() => useTasksTabAccess())
    expect(result.current.visibleTabs).toEqual([TASKS_TAB_APPROVALS, TASKS_TAB_FORM_RESPONSES])
    expect(result.current.canViewTasks).toBe(true)
    expect(result.current.isError).toBe(false)
  })

  it('exposes only Approvals when the user can read approvals but not form prompts', () => {
    mockUseFormPromptPermissions.mockReturnValue({ canRead: false, isChecking: false, isError: false })

    const { result } = renderHook(() => useTasksTabAccess())
    expect(result.current.visibleTabs).toEqual([TASKS_TAB_APPROVALS])
    expect(result.current.canViewApprovals).toBe(true)
    expect(result.current.canViewFormResponses).toBe(false)
    expect(result.current.canViewTasks).toBe(true)
  })

  it('exposes only Form responses when the user can read form prompts but not approvals', () => {
    mockUseApprovalPermissions.mockReturnValue({ canRead: false, isChecking: false, isError: false })

    const { result } = renderHook(() => useTasksTabAccess())
    expect(result.current.visibleTabs).toEqual([TASKS_TAB_FORM_RESPONSES])
    expect(result.current.canViewApprovals).toBe(false)
    expect(result.current.canViewFormResponses).toBe(true)
    expect(result.current.canViewTasks).toBe(true)
  })

  it('denies Tasks when neither approval nor form prompt read is granted', () => {
    mockUseApprovalPermissions.mockReturnValue({ canRead: false, isChecking: false, isError: false })
    mockUseFormPromptPermissions.mockReturnValue({ canRead: false, isChecking: false, isError: false })

    const { result } = renderHook(() => useTasksTabAccess())
    expect(result.current.visibleTabs).toEqual([])
    expect(result.current.canViewTasks).toBe(false)
  })

  it('surfaces isError when either permission hook errors', () => {
    mockUseApprovalPermissions.mockReturnValue({ canRead: true, isChecking: false, isError: true })

    const { result } = renderHook(() => useTasksTabAccess())
    expect(result.current.isError).toBe(true)
  })

  it('surfaces isError from the form prompt permission hook', () => {
    mockUseFormPromptPermissions.mockReturnValue({ canRead: true, isChecking: false, isError: true })

    const { result } = renderHook(() => useTasksTabAccess())
    expect(result.current.isError).toBe(true)
  })

  it('aggregates isChecking from either permission hook', () => {
    mockUseFormPromptPermissions.mockReturnValue({ canRead: true, isChecking: true, isError: false })

    const { result } = renderHook(() => useTasksTabAccess())
    expect(result.current.isChecking).toBe(true)
  })

  it('aggregates isChecking from the approval permission hook', () => {
    mockUseApprovalPermissions.mockReturnValue({ canRead: true, isChecking: true, isError: false })

    const { result } = renderHook(() => useTasksTabAccess())
    expect(result.current.isChecking).toBe(true)
  })
})
