import type { WorkflowAPI } from '@syntara/contracts'

import { useVersionDefinitionPermissions } from './useVersionDefinitionPermissions'

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

export function useBuilderVersionPermissions(options: {
  canEdit: boolean
  projectId?: string
  isViewingVersion: boolean
  viewedVersion?: number | null
  viewedVersionDate?: string | null
  viewedVersionDefinition?: Record<string, unknown>
  viewedVersionIsLoading: boolean
  retryViewedVersion: () => Promise<unknown>
  editVersion?: WorkflowVersion
  isEditDialogOpen: boolean
  restoreDefinition?: Record<string, unknown>
  isRestoreDialogOpen: boolean
  publishDefinition?: Record<string, unknown>
  isPublishDialogOpen: boolean
}) {
  const selected = useVersionDefinitionPermissions(options.viewedVersionDefinition, options.projectId, {
    enabled: options.isViewingVersion,
    isContextLoading: options.viewedVersionIsLoading,
    retryContext: options.retryViewedVersion,
  })
  const edit = useVersionDefinitionPermissions(options.editVersion?.workflow_definition, options.projectId, {
    enabled: options.isEditDialogOpen,
    isContextLoading: options.isEditDialogOpen && !options.editVersion,
  })
  const restore = useVersionDefinitionPermissions(options.restoreDefinition, options.projectId, {
    enabled: options.isRestoreDialogOpen,
    isContextLoading: options.isRestoreDialogOpen && !options.restoreDefinition,
  })
  const publish = useVersionDefinitionPermissions(options.publishDefinition, options.projectId, {
    enabled: options.isPublishDialogOpen,
    isContextLoading: options.isPublishDialogOpen && !options.publishDefinition,
  })

  return {
    canRestoreSelectedVersion:
      options.canEdit &&
      options.isViewingVersion &&
      options.viewedVersionDate != null &&
      options.viewedVersion != null &&
      selected.canAuthor,
    restoreTooltip: options.canEdit ? selected.permissionMessage : undefined,
    selectedVersionPermissionError: selected.isError,
    selectedVersionPermissionLoading: options.isViewingVersion && selected.isChecking,
    retrySelectedVersionPermissions: selected.retry,
    canEditSelectedVersion: options.canEdit && edit.canAuthor,
    editVersionTooltip: options.canEdit ? edit.permissionMessage : 'You do not have permission to edit this workflow.',
    editPermissionCheckError: edit.isError,
    retryEditPermissions: edit.retry,
    canConfirmRestore: options.canEdit && restore.canAuthor,
    restorePermissionCheckError: restore.isError,
    restorePermissionCheckLoading: restore.isChecking,
    restoreBlockedStepTypes: restore.blockedStepTypes.map((type) => type.label),
    retryRestorePermissions: restore.retry,
    canPublishSelectedVersion: options.canEdit && publish.canAuthor,
    publishTargetTooltip: options.canEdit
      ? publish.permissionMessage
      : 'You do not have permission to publish this workflow.',
    publishPermissionCheckError: publish.isError,
    publishPermissionCheckLoading: publish.isChecking,
    publishBlockedStepTypes: publish.blockedStepTypes.map((type) => type.label),
    retryPublishPermissions: publish.retry,
  }
}
