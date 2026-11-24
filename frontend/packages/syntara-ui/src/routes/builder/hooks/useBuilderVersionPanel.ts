import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, type Dispatch } from 'react'

import { useDialogState } from '../../../hooks/useDialogState'
import { useAlerts } from '../../../providers/alerts/AlertContext'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { detachPromise } from '../../../utils/detachPromise'
import { formatStepTypeLabels } from '../../../utils/nodeKindDenials'
import type { BuilderAction } from '../builderReducer'

import { useBuilderVersionHistory } from './useBuilderVersionHistory'
import { useBuilderVersionPermissions } from './useBuilderVersionPermissions'
import type { useVersionDefinitionPermissions } from './useVersionDefinitionPermissions'
import { useVersionViewNavigation } from './useVersionViewNavigation'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']
type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']
type ResourceDialog<T> = { isOpen: boolean; item: T | null; open: (item: T) => void; close: () => void }
type VersionDefinitionPermissions = ReturnType<typeof useVersionDefinitionPermissions>

function getRestoreTooltip(permissions: VersionDefinitionPermissions) {
  if (permissions.isChecking || permissions.isError || !permissions.blockedStepTypes.length) {
    return permissions.permissionMessage || undefined
  }
  const stepTypes = formatStepTypeLabels(permissions.blockedStepTypes)
  return `You can’t restore this version because you don’t have permission to edit ${stepTypes} steps.`
}

function buildPublishDialogProps(options: {
  canEdit: boolean
  canPublish: boolean
  publishPermissions: VersionDefinitionPermissions
  versionPublishDialog: ResourceDialog<number>
  publishVersion: (version: number, publishName?: string, description?: string) => void
}) {
  const { canEdit, canPublish, publishPermissions, versionPublishDialog, publishVersion } = options
  return {
    isOpen: versionPublishDialog.isOpen,
    onClose: versionPublishDialog.close,
    canPublish,
    permissionCheckError: publishPermissions.isError,
    permissionCheckLoading: publishPermissions.isChecking,
    blockedStepTypes: publishPermissions.blockedStepTypes.map((type) => type.label),
    editTooltip: canEdit
      ? publishPermissions.permissionMessage
      : 'You do not have permission to publish this workflow.',
    onRetryPermissionCheck: publishPermissions.retry,
    onPublish: (publishName?: string, description?: string) => {
      if (canPublish && versionPublishDialog.item != null) {
        publishVersion(versionPublishDialog.item, publishName, description)
        versionPublishDialog.close()
      }
    },
  }
}

function buildRestoreDialogProps(options: {
  canConfirm: boolean
  restorePermissions: VersionDefinitionPermissions
  restoreDialog: ReturnType<typeof useBuilderVersionHistory>['restoreDialog']
  restoreDialogTitle: string
  restoreMutationIsPending: boolean
  handleConfirmRestore: () => void
}) {
  const {
    canConfirm,
    restorePermissions,
    restoreDialog,
    restoreDialogTitle,
    restoreMutationIsPending,
    handleConfirmRestore,
  } = options
  return {
    isOpen: restoreDialog.isOpen,
    title: restoreDialogTitle,
    isLoading: restoreMutationIsPending,
    canConfirm,
    permissionCheckError: restorePermissions.isError,
    permissionCheckLoading: restorePermissions.isChecking,
    blockedStepTypes: restorePermissions.blockedStepTypes.map((type) => type.label),
    onRetryPermissionCheck: restorePermissions.retry,
    onClose: restoreDialog.close,
    onConfirm: () => {
      if (canConfirm) handleConfirmRestore()
    },
  }
}

function editDialogTooltip(canEdit: boolean, canEditSelected: boolean, permissionMessage: string): string | undefined {
  if (canEditSelected) return undefined
  return canEdit ? permissionMessage : 'You do not have permission to edit this workflow.'
}

function buildEditDialogProps(options: {
  canEdit: boolean
  editPermissions: VersionDefinitionPermissions
  editVersionDialog: ResourceDialog<WorkflowVersion>
  isSaving: boolean
  updateVersionMetadata: ReturnType<typeof useBuilderVersionHistory>['updateVersionMetadata']
}) {
  const { canEdit, editPermissions, editVersionDialog, isSaving, updateVersionMetadata } = options
  const canEditSelected = canEdit && editPermissions.canAuthor
  return {
    isOpen: editVersionDialog.isOpen,
    isSaving,
    onClose: editVersionDialog.close,
    onSave: (name: string | null, description: string | null) => {
      if (!canEditSelected || !editVersionDialog.item) return
      updateVersionMetadata(editVersionDialog.item.version, name, description)
      editVersionDialog.close()
    },
    canEdit: canEditSelected,
    editTooltip: editDialogTooltip(canEdit, canEditSelected, editPermissions.permissionMessage),
    permissionCheckError: editPermissions.isError,
    onRetryPermissionCheck: editPermissions.retry,
    initialName: editVersionDialog.item?.name,
    initialDescription: editVersionDialog.item?.change_description,
  }
}

type UseBuilderVersionPanelParams = {
  workflowId: string | null
  isNew: boolean
  workflow: WorkflowWithVersion | undefined
  viewingVersion: number | null
  versionHistoryOpen: boolean
  dispatch: Dispatch<BuilderAction>
  handleSaveWorkflow: () => Promise<boolean>
  expandAllEvent: EventTarget
  baseHandleToggleVersionHistory: () => void
  searchParams: URLSearchParams
  setSearchParams: (params: URLSearchParams) => void
  onOpenRunHistory: (versionNumber: number) => void
  onClearExecutionFilters: () => void
  executedVersionNumbers: Map<number, string>
  onDuplicateVersion: (version: WorkflowVersion) => void
  onVersionUpdated?: (version: number) => void
  canEdit: boolean
  canCreate: boolean
  saveTooltip: string
}

export function useBuilderVersionPanel(params: UseBuilderVersionPanelParams) {
  const {
    workflowId,
    isNew,
    workflow,
    viewingVersion,
    versionHistoryOpen,
    dispatch,
    handleSaveWorkflow,
    expandAllEvent,
    baseHandleToggleVersionHistory,
    searchParams,
    setSearchParams,
    onOpenRunHistory,
    onClearExecutionFilters,
    executedVersionNumbers,
    onDuplicateVersion,
    onVersionUpdated,
    canEdit,
    canCreate,
    saveTooltip,
  } = params
  const { isDirty } = useWorkflowStore()
  const { showSuccess, showError } = useAlerts()

  const {
    filteredVersions,
    publishedVersionName,
    statusFilter,
    setStatusFilter,
    exportVersion,
    openInNewWindow,
    publishVersion,
    isViewingVersion,
    viewedVersionDate,
    viewedVersionStatus,
    viewedVersionDescription,
    viewedVersionName,
    viewedVersionPublishedAt,
    viewedVersionUnpublishedAt,
    viewedVersionDefinition,
    viewedVersionIsLoading,
    refetchViewedVersion,
    handleExitVersionView,
    handleConfirmRestore,
    restoreDialog,
    restoreDialogTitle,
    restoreMutation,
    versionsQuery,
    updateVersionMetadata,
    updateMetadataMutation,
    paginationFooterProps,
  } = useBuilderVersionHistory({
    workflowId,
    isNew,
    workflow,
    viewingVersion,
    dispatch,
    showSuccess,
    showError,
    expandAllEvent,
    searchParams,
    setSearchParams,
    onVersionUpdated,
  })

  const { refetch: refetchVersions } = versionsQuery

  const handleToggleVersionHistory = useCallback(() => {
    baseHandleToggleVersionHistory()
    if (!versionHistoryOpen) {
      onClearExecutionFilters()
      detachPromise(refetchVersions())
    }
  }, [baseHandleToggleVersionHistory, versionHistoryOpen, onClearExecutionFilters, refetchVersions])

  const versionPublishDialog = useDialogState<number>()
  const editVersionDialog = useDialogState<WorkflowVersion>()
  const publishTargetVersion = filteredVersions.find((version) => version.version === versionPublishDialog.item)
  const {
    selected: selectedVersionPermissions,
    edit: editPermissions,
    restore: restorePermissions,
    publish: publishPermissions,
  } = useBuilderVersionPermissions({
    projectId: workflow?.project_id,
    isViewingVersion,
    viewedVersionDefinition,
    viewedVersionIsLoading,
    retryViewedVersion: () => refetchViewedVersion(),
    editVersion: editVersionDialog.item ?? undefined,
    isEditDialogOpen: editVersionDialog.isOpen,
    restoreDefinition: restoreDialog.item?.definition,
    isRestoreDialogOpen: restoreDialog.isOpen,
    publishDefinition: publishTargetVersion?.workflow_definition,
    isPublishDialogOpen: versionPublishDialog.isOpen,
  })

  const canRestoreSelectedVersion =
    canEdit &&
    isViewingVersion &&
    viewingVersion !== null &&
    viewedVersionDate != null &&
    selectedVersionPermissions.canAuthor

  const handleViewRunHistory = (versionNumber: number) => {
    if (isViewingVersion) {
      handleExitVersionView()
    } else {
      dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
    }
    onOpenRunHistory(versionNumber)
  }

  const versionNavigation = useVersionViewNavigation({
    isDirty,
    isViewingVersion,
    canSave: canEdit,
    dispatch,
    handleSaveWorkflow,
    searchParams,
    setSearchParams,
  })

  const openRestoreDialogForCurrentVersion = isViewingVersion
    ? () => {
        if (!canRestoreSelectedVersion || viewingVersion === null || !viewedVersionDate || !viewedVersionDefinition)
          return
        restoreDialog.open({
          version: viewingVersion,
          dateTime: viewedVersionDate,
          definition: viewedVersionDefinition,
        })
      }
    : undefined

  const versionSidePanel = {
    show: !isNew && !!workflowId && versionHistoryOpen,
    filteredVersions,
    publishedVersionName,
    selectedVersion: viewingVersion,
    statusFilter,
    onStatusFilterChange: setStatusFilter,
    paginationFooterProps,
    onClose: () => dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: false }),
    onSelectVersion: versionNavigation.onSelectVersion,
    onRestoreVersion: ({ version, created_at, workflow_definition }: WorkflowVersion) => {
      if (canEdit) restoreDialog.open({ version, dateTime: created_at, definition: workflow_definition })
    },
    onExportVersion: exportVersion,
    onOpenInNewWindow: openInNewWindow,
    onPublishVersion: (version: number) => {
      if (canEdit) versionPublishDialog.open(version)
    },
    onViewRunHistory: handleViewRunHistory,
    executedVersionNumbers,
    onEditVersion: (version: WorkflowVersion) => {
      if (canEdit) editVersionDialog.open(version)
    },
    onDuplicateVersion: (version: WorkflowVersion) => {
      if (canCreate) onDuplicateVersion(version)
    },
    publishDialog: buildPublishDialogProps({
      canEdit,
      canPublish: canEdit && publishPermissions.canAuthor,
      publishPermissions,
      versionPublishDialog,
      publishVersion,
    }),
    saveBeforeViewDialog: { ...versionNavigation.saveBeforeViewDialog, canSave: canEdit, saveTooltip },
    restoreDialog: buildRestoreDialogProps({
      canConfirm: canEdit && restorePermissions.canAuthor,
      restorePermissions,
      restoreDialog,
      restoreDialogTitle,
      restoreMutationIsPending: restoreMutation.isPending,
      handleConfirmRestore,
    }),
    editDialog: buildEditDialogProps({
      canEdit,
      editPermissions,
      editVersionDialog,
      isSaving: updateMetadataMutation.isPending,
      updateVersionMetadata,
    }),
  }

  return {
    isViewingVersion,
    viewedVersionDate,
    viewedVersionStatus,
    viewedVersionDescription,
    viewedVersionName,
    viewedVersionPublishedAt,
    viewedVersionUnpublishedAt,
    handleExitVersionView,
    handleToggleVersionHistory,
    openRestoreDialogForCurrentVersion,
    canRestoreSelectedVersion,
    restoreTooltip: getRestoreTooltip(selectedVersionPermissions),
    selectedVersionPermissionError: selectedVersionPermissions.isError,
    selectedVersionPermissionLoading: isViewingVersion && selectedVersionPermissions.isChecking,
    retrySelectedVersionPermissions: selectedVersionPermissions.retry,

    versionSidePanel,
  }
}

export type UseBuilderVersionPanelReturn = ReturnType<typeof useBuilderVersionPanel>
export type VersionSidePanelState = UseBuilderVersionPanelReturn['versionSidePanel']
