import { Alert, AlertActionLink, StackItem } from '@patternfly/react-core'
import { useState } from 'react'

import { formatStepTypeWriteDenial } from '../../utils/nodeKindDenials'
import type { BlockedStepType } from '../workflows/useStepTypePermissions'

type BuilderReadOnlyBannerProps = Readonly<{
  canEdit: boolean
  isLoading: boolean
  isBuiltin: boolean
  blockedStepTypes?: BlockedStepType[]
  permissionCheckError?: boolean
  onRetryPermissionCheck?: () => void
  runUsesSavedVersion?: boolean
}>

type PermissionStatus = 'checking' | 'error' | 'read-only' | 'editable'

function usePermissionAnnouncement(status: PermissionStatus) {
  const [previous, setPrevious] = useState({
    status,
    message: '',
    needsRecovery: status !== 'editable' && status !== 'checking',
  })
  if (previous.status !== status) {
    const messages = {
      checking: '',
      error: 'Unable to check step-type permissions.',
      'read-only': 'Editing is unavailable. This workflow is read-only.',
      editable: 'Editing access restored.',
    }
    const message = status === 'editable' && !previous.needsRecovery ? '' : messages[status]
    const needsRecovery = status === 'checking' ? previous.needsRecovery : status !== 'editable'
    setPrevious({ status, message, needsRecovery })
    return message
  }
  return previous.message
}

export function BuilderReadOnlyBanner({
  canEdit,
  isLoading,
  isBuiltin,
  blockedStepTypes = [],
  permissionCheckError = false,
  onRetryPermissionCheck,
  runUsesSavedVersion = false,
}: BuilderReadOnlyBannerProps) {
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

  let status: PermissionStatus = canEdit ? 'editable' : 'read-only'
  if (isLoading) status = 'checking'
  if (permissionCheckError) status = 'error'
  const announcement = usePermissionAnnouncement(status)
  const showAlert = status === 'error' || status === 'read-only' || runUsesSavedVersion
  if (runUsesSavedVersion) {
    if (status === 'checking') {
      title = 'Checking editing permissions.'
      description = 'Authoring controls are disabled while permissions are checked.'
    }
    description += ' Run uses the last saved version.'
  }

  return (
    <>
      <span role="status" className="pf-v6-u-screen-reader">
        {announcement}
      </span>
      {showAlert && (
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
      )}
    </>
  )
}
