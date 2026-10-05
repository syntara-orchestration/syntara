import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { TASKS_TAB_APPROVALS, TASKS_TAB_FORM_RESPONSES, useTasksTabAccess } from './useTasksTabAccess'

vi.mock('../approvals/useApprovalPermissions', () => ({
  useApprovalPermissions: () => ({ canRead: true, isChecking: false, isError: false }),
}))

vi.mock('../executions/hooks/useFormPromptPermissions', () => ({
  useFormPromptPermissions: () => ({ canRead: true, isChecking: false, isError: false }),
}))

describe('useTasksTabAccess', () => {
  it('exposes both tabs when the user can read approvals and form prompts', () => {
    const { result } = renderHook(() => useTasksTabAccess())
    expect(result.current.visibleTabs).toEqual([TASKS_TAB_APPROVALS, TASKS_TAB_FORM_RESPONSES])
    expect(result.current.canViewTasks).toBe(true)
    expect(result.current.isError).toBe(false)
  })
})
