import { useMemo } from 'react'

import { isSystemScope, permissionTooltip, projectScopedNames } from '../../../hooks/permissionUtils'
import { useCanI } from '../../../hooks/useCanI'
import { useAllPermissions } from '../../access/useAllPermissions'

/** Permission checks for form prompt read/submit in execution and tasks flows. */
export function useFormPromptPermissions(projectId?: string | null) {
  const canReadGlobalQuery = useCanI('read', 'form_prompt')
  const canSubmitGlobalQuery = useCanI('submit', 'form_prompt')
  const canSubmitProjectQuery = useCanI('submit', 'form_prompt', projectId ? { resourceProject: projectId } : undefined)

  const canReadProjectQuery = useCanI('read', 'form_prompt', projectId ? { resourceProject: projectId } : undefined)
  const { permissions, isLoading: isLoadingAllPermissions } = useAllPermissions()

  const { canReadAnyProject, canSubmitAnyProject } = useMemo(() => {
    const readEntries = permissions.filter((p) => p.effect === 'allow' && p.actions.includes('form_prompt:read'))
    const submitEntries = permissions.filter((p) => p.effect === 'allow' && p.actions.includes('form_prompt:submit'))
    return {
      canReadAnyProject: readEntries.some(isSystemScope) || projectScopedNames(readEntries).size > 0,
      canSubmitAnyProject: submitEntries.some(isSystemScope) || projectScopedNames(submitEntries).size > 0,
    }
  }, [permissions])

  return useMemo(() => {
    const canSubmit = canSubmitGlobalQuery.allowed || canSubmitProjectQuery.allowed || canSubmitAnyProject
    const canRead = canReadGlobalQuery.allowed || canReadProjectQuery.allowed || canReadAnyProject

    return {
      canRead,
      canSubmit,
      isChecking:
        canReadGlobalQuery.isChecking ||
        canReadProjectQuery.isChecking ||
        canSubmitGlobalQuery.isChecking ||
        canSubmitProjectQuery.isChecking ||
        isLoadingAllPermissions,
      isError:
        canReadGlobalQuery.isError ||
        canReadProjectQuery.isError ||
        canSubmitGlobalQuery.isError ||
        canSubmitProjectQuery.isError,
      tooltips: {
        submit: permissionTooltip('submit this form', 'form_prompt:submit'),
      },
    }
  }, [
    canReadGlobalQuery.allowed,
    canReadGlobalQuery.isChecking,
    canReadGlobalQuery.isError,
    canReadProjectQuery.allowed,
    canReadProjectQuery.isChecking,
    canReadProjectQuery.isError,
    canSubmitGlobalQuery.allowed,
    canSubmitGlobalQuery.isChecking,
    canSubmitGlobalQuery.isError,
    canSubmitProjectQuery.allowed,
    canSubmitProjectQuery.isChecking,
    canSubmitProjectQuery.isError,
    canReadAnyProject,
    canSubmitAnyProject,
    isLoadingAllPermissions,
  ])
}
