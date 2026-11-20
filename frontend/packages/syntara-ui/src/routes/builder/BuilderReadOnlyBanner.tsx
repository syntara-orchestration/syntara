import { Alert, AlertActionLink, StackItem } from '@patternfly/react-core'

import { formatStepTypeWriteDenial } from '../../utils/nodeKindDenials'
import type { BlockedStepType } from '../workflows/useStepTypePermissions'

type BuilderReadOnlyBannerProps = Readonly<{
  canEdit: boolean
  isLoading: boolean
  isBuiltin: boolean
  blockedStepTypes?: BlockedStepType[]
  permissionCheckError?: boolean
  onRetryPermissionCheck?: () => void
}>

export function BuilderReadOnlyBanner({
  canEdit,
  isLoading,
  isBuiltin,
  blockedStepTypes = [],
  permissionCheckError = false,
  onRetryPermissionCheck,
}: BuilderReadOnlyBannerProps) {
  if ((canEdit || isLoading) && !permissionCheckError) return null

  let title = 'You are viewing this workflow in read-only mode.'
  let description = 'You do not have permission to edit this workflow. Contact your administrator to request access.'
  if (permissionCheckError) {
    title = 'Unable to check step-type permissions.'
    description = 'Authoring controls are disabled until step-type permissions can be checked.'
  } else if (isBuiltin) {
    title = 'This is a built-in workflow.'
    description = 'Built-in workflows cannot be modified.'
  } else if (blockedStepTypes.length > 0) {
    description = formatStepTypeWriteDenial(blockedStepTypes)
  }

  return (
    <StackItem>
      <Alert
        variant={permissionCheckError ? 'danger' : 'info'}
        isInline
        title={title}
        actionLinks={
          permissionCheckError && onRetryPermissionCheck ? (
            <AlertActionLink onClick={onRetryPermissionCheck}>Retry permission check</AlertActionLink>
          ) : undefined
        }
      >
        {description}
      </Alert>
    </StackItem>
  )
}
