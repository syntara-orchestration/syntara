import { useMemo } from 'react'

import { useApprovalPermissions } from '../approvals/useApprovalPermissions'
import { useFormPromptPermissions } from '../executions/hooks/useFormPromptPermissions'

export const TASKS_TAB_APPROVALS = 'approvals'
export const TASKS_TAB_FORM_RESPONSES = 'form-responses'

export function useTasksTabAccess() {
  const approvalPermissions = useApprovalPermissions()
  const formPromptPermissions = useFormPromptPermissions()

  return useMemo(() => {
    const canViewApprovals = approvalPermissions.canRead
    const canViewFormResponses = formPromptPermissions.canRead
    const visibleTabs: string[] = []
    if (canViewApprovals) visibleTabs.push(TASKS_TAB_APPROVALS)
    if (canViewFormResponses) visibleTabs.push(TASKS_TAB_FORM_RESPONSES)

    return {
      canViewApprovals,
      canViewFormResponses,
      visibleTabs,
      isChecking: approvalPermissions.isChecking || formPromptPermissions.isChecking,
      isError: approvalPermissions.isError || formPromptPermissions.isError,
      canViewTasks: canViewApprovals || canViewFormResponses,
    }
  }, [
    approvalPermissions.canRead,
    approvalPermissions.isChecking,
    approvalPermissions.isError,
    formPromptPermissions.canRead,
    formPromptPermissions.isChecking,
    formPromptPermissions.isError,
  ])
}
