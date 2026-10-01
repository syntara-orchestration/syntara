import { useMemo } from 'react'

import { permissionTooltip } from '../../../hooks/permissionUtils'
import { useCanI } from '../../../hooks/useCanI'

/** Permission checks for form prompt read/submit in execution and tasks flows. */
export function useFormPromptPermissions(projectId?: string | null) {
  const canReadGlobalQuery = useCanI('read', 'form_prompt')
  const canSubmitGlobalQuery = useCanI('submit', 'form_prompt')
  const canSubmitProjectQuery = useCanI('submit', 'form_prompt', projectId ? { resourceProject: projectId } : undefined)

  const canReadProjectQuery = useCanI('read', 'form_prompt', projectId ? { resourceProject: projectId } : undefined)

  return useMemo(() => {
    const canSubmit = canSubmitGlobalQuery.allowed || canSubmitProjectQuery.allowed
    const canRead = canReadGlobalQuery.allowed || canReadProjectQuery.allowed

    return {
      canRead,
      canSubmit,
      isChecking:
        canReadGlobalQuery.isChecking ||
        canReadProjectQuery.isChecking ||
        canSubmitGlobalQuery.isChecking ||
        canSubmitProjectQuery.isChecking,
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
  ])
}
