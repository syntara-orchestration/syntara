import { Alert, AlertActionLink, StackItem } from '@patternfly/react-core'

type BuilderReadOnlyBannerProps = Readonly<{
  canEdit: boolean
  isLoading: boolean
  isBuiltin: boolean
  blockedStepTypes?: string[]
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

  const isStepTypeReadOnly = blockedStepTypes.length > 0
  let title = 'You are viewing this workflow in read-only mode.'
  let description = 'You do not have permission to edit this workflow. Contact your administrator to request access.'
  if (permissionCheckError) {
    title = 'Unable to check step-type permissions.'
    description = 'Authoring controls are disabled until step-type permissions can be checked.'
  } else if (isBuiltin) {
    title = 'This is a built-in workflow.'
    description = 'Built-in workflows cannot be modified.'
  } else if (isStepTypeReadOnly) {
    description = `Blocked step types: ${blockedStepTypes.join(', ')}.`
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
