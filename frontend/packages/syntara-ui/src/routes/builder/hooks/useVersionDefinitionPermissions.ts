import { useMemo } from 'react'

import { getStepTypesFromDefinition, useStepTypePermissions } from '../../workflows/useStepTypePermissions'

export function useVersionDefinitionPermissions(
  definition: Record<string, unknown> | undefined,
  projectId: string | undefined,
  options: { enabled: boolean; isContextLoading?: boolean; retryContext?: () => Promise<unknown> }
) {
  const stepTypes = useMemo(() => getStepTypesFromDefinition(definition), [definition])
  const hasContext = stepTypes !== undefined
  const permissions = useStepTypePermissions(stepTypes, projectId, {
    enabled: options.enabled && hasContext && !options.isContextLoading,
    retryContext: options.retryContext,
  })
  const isChecking = options.enabled && (options.isContextLoading === true || permissions.isChecking)
  const isError = options.enabled && !isChecking && (!hasContext || permissions.isError)
  const canAuthor = !options.enabled || (!isChecking && !isError && hasContext && permissions.canAuthor)
  let permissionMessage = ''
  if (isError) permissionMessage = 'Unable to check the selected version step types. Retry the permission check.'
  else if (isChecking) permissionMessage = 'Checking the selected version step types.'
  else if (permissions.blockedStepTypes.length > 0) {
    permissionMessage = `Blocked step types: ${permissions.blockedStepTypes.map((type) => type.label).join(', ')}.`
  }

  return {
    canAuthor,
    isChecking,
    isError,
    blockedStepTypes: permissions.blockedStepTypes,
    permissionMessage,
    retry: permissions.retry,
  }
}
