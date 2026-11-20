import type { WorkflowAPI } from '@syntara/contracts'

import { useVersionDefinitionPermissions } from './useVersionDefinitionPermissions'

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']

/**
 * Step-type write permission checks for the four version surfaces that need
 * them: the currently viewed version, and the open edit/restore/publish
 * dialogs. Each result carries `canAuthor`, `isChecking`, `isError`,
 * `blockedStepTypes`, `permissionMessage` and `retry`; combine with the
 * builder's RBAC `canEdit` at the call site.
 */
export function useBuilderVersionPermissions(options: {
  projectId?: string
  isViewingVersion: boolean
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

  return { selected, edit, restore, publish }
}
