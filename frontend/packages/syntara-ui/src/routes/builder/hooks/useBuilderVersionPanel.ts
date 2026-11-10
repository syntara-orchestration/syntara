import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, type Dispatch } from 'react'

import { useDialogState } from '../../../hooks/useDialogState'
import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { detachPromise } from '../../../utils/detachPromise'
import type { BuilderAction } from '../builderReducer'

import { useBuilderVersionHistory } from './useBuilderVersionHistory'
import { useBuilderVersionPermissions } from './useBuilderVersionPermissions'
import { useVersionViewNavigation } from './useVersionViewNavigation'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']
type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']
type VersionHistoryState = ReturnType<typeof useBuilderVersionHistory>
type ResourceDialog<T> = { isOpen: boolean; item: T | null; open: (item: T) => void; close: () => void }
type RestoreDialogItem = { version: number; dateTime: string }

type VersionSidePanelOptions = {
  workflowId: string | null
  isNew: boolean
  versionHistoryOpen: boolean
  dispatch: Dispatch<BuilderAction>
  filteredVersions: VersionHistoryState['filteredVersions']
  publishedVersionName: string | null
  selectedVersion: number | null
  statusFilter: VersionHistoryState['statusFilter']
  setStatusFilter: VersionHistoryState['setStatusFilter']
  paginationFooterProps: VersionHistoryState['paginationFooterProps']
  onSelectVersion: (version: number) => void
  onExportVersion: (version: number) => void
  onOpenInNewWindow: (version: number) => void
  onViewRunHistory: (versionNumber: number) => void
  executedVersionNumbers: Map<number, string>
  restoreDialog: ResourceDialog<RestoreDialogItem>
  restoreDialogTitle: string
  restoreMutationIsPending: boolean
  canConfirmRestore: boolean
  restorePermissionCheckError: boolean
  restorePermissionCheckLoading: boolean
  restoreBlockedStepTypes: string[]
  retryRestorePermissions: () => Promise<void>
  handleConfirmRestore: () => void
  versionPublishDialog: ResourceDialog<number>
  canPublishSelectedVersion: boolean
  publishPermissionCheckError: boolean
  publishPermissionCheckLoading: boolean
  publishBlockedStepTypes: string[]
  publishTargetTooltip: string
  retryPublishPermissions: () => Promise<void>
  publishVersion: (version: number, publishName?: string, description?: string) => void
  saveBeforeViewDialog: {
    isOpen: boolean
    onSave: () => Promise<boolean>
    onViewWithoutSaving: () => void
    onCancel: () => void
  }
  editVersionDialog: ResourceDialog<WorkflowVersion>
  canEditSelectedVersion: boolean
  editVersionTooltip: string
  editPermissionCheckError: boolean
  retryEditPermissions: () => Promise<void>
  isSavingVersionMetadata: boolean
  handleEditVersionSave: (name: string | null, description: string | null) => void
  canCreate: boolean
  canEdit: boolean
  onDuplicateVersion: (version: WorkflowVersion) => void
}

function buildVersionSidePanel(options: VersionSidePanelOptions) {
  return {
    show: !options.isNew && !!options.workflowId && options.versionHistoryOpen,
    filteredVersions: options.filteredVersions,
    publishedVersionName: options.publishedVersionName,
    selectedVersion: options.selectedVersion,
    statusFilter: options.statusFilter,
    onStatusFilterChange: options.setStatusFilter,
    paginationFooterProps: options.paginationFooterProps,
    onClose: () => options.dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: false }),
    onSelectVersion: options.onSelectVersion,
    onRestoreVersion: (version: number, createdAt: string) => {
      if (options.canEdit) options.restoreDialog.open({ version, dateTime: createdAt })
    },
    onExportVersion: options.onExportVersion,
    onOpenInNewWindow: options.onOpenInNewWindow,
    onPublishVersion: (version: number) => {
      if (options.canEdit) options.versionPublishDialog.open(version)
    },
    onViewRunHistory: options.onViewRunHistory,
    executedVersionNumbers: options.executedVersionNumbers,
    onEditVersion: (version: WorkflowVersion) => {
      if (options.canEdit) options.editVersionDialog.open(version)
    },
    onDuplicateVersion: (version: WorkflowVersion) => {
      if (options.canCreate) options.onDuplicateVersion(version)
    },
    publishDialog: {
      isOpen: options.versionPublishDialog.isOpen,
      onClose: options.versionPublishDialog.close,
      canPublish: options.canPublishSelectedVersion,
      permissionCheckError: options.publishPermissionCheckError,
      permissionCheckLoading: options.publishPermissionCheckLoading,
      blockedStepTypes: options.publishBlockedStepTypes,
      editTooltip: options.publishTargetTooltip,
      onRetryPermissionCheck: options.retryPublishPermissions,
      onPublish: (publishName?: string, description?: string) => {
        if (options.canPublishSelectedVersion && options.versionPublishDialog.item != null) {
          options.publishVersion(options.versionPublishDialog.item, publishName, description)
          options.versionPublishDialog.close()
        }
      },
    },
    saveBeforeViewDialog: options.saveBeforeViewDialog,
    restoreDialog: {
      isOpen: options.restoreDialog.isOpen,
      title: options.restoreDialogTitle,
      isLoading: options.restoreMutationIsPending,
      canConfirm: options.canConfirmRestore,
      permissionCheckError: options.restorePermissionCheckError,
      permissionCheckLoading: options.restorePermissionCheckLoading,
      blockedStepTypes: options.restoreBlockedStepTypes,
      onRetryPermissionCheck: options.retryRestorePermissions,
      onClose: options.restoreDialog.close,
      onConfirm: () => {
        if (options.canConfirmRestore) options.handleConfirmRestore()
      },
    },
    editDialog: {
      isOpen: options.editVersionDialog.isOpen,
      isSaving: options.isSavingVersionMetadata,
      onClose: options.editVersionDialog.close,
      onSave: options.handleEditVersionSave,
      canEdit: options.canEditSelectedVersion,
      editTooltip: options.canEditSelectedVersion ? undefined : options.editVersionTooltip,
      permissionCheckError: options.editPermissionCheckError,
      onRetryPermissionCheck: options.retryEditPermissions,
      initialName: options.editVersionDialog.item?.name,
      initialDescription: options.editVersionDialog.item?.change_description,
    },
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
  workflowName: string
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
  const restoreTargetVersion = filteredVersions.find((version) => version.version === restoreDialog.item?.version)
  const publishTargetVersion = filteredVersions.find((version) => version.version === versionPublishDialog.item)
  const versionPermissions = useBuilderVersionPermissions({
    canEdit,
    projectId: workflow?.project_id,
    isViewingVersion,
    viewedVersion: viewingVersion,
    viewedVersionDate,
    viewedVersionDefinition,
    viewedVersionIsLoading,
    retryViewedVersion: () => refetchViewedVersion(),
    editVersion: editVersionDialog.item ?? undefined,
    isEditDialogOpen: editVersionDialog.isOpen,
    restoreDefinition: restoreTargetVersion?.workflow_definition,
    isRestoreDialogOpen: restoreDialog.isOpen,
    publishDefinition: publishTargetVersion?.workflow_definition,
    isPublishDialogOpen: versionPublishDialog.isOpen,
  })

  const handleEditVersionSave = useCallback(
    (publishName: string | null, changeDescription: string | null) => {
      if (!versionPermissions.canEditSelectedVersion || !editVersionDialog.item) return
      updateVersionMetadata(editVersionDialog.item.version, publishName, changeDescription)
      editVersionDialog.close()
    },
    [versionPermissions.canEditSelectedVersion, editVersionDialog, updateVersionMetadata]
  )

  const handleViewRunHistory = useCallback(
    (versionNumber: number) => {
      if (isViewingVersion) {
        handleExitVersionView()
      } else {
        dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
      }
      onOpenRunHistory(versionNumber)
    },
    [isViewingVersion, handleExitVersionView, dispatch, onOpenRunHistory]
  )

  const setVersionParam = useCallback(
    (version: number) => {
      const params = new URLSearchParams(searchParams)
      params.set('version', String(version))
      setSearchParams(params)
    },
    [searchParams, setSearchParams]
  )
  const versionNavigation = useVersionViewNavigation({
    isDirty,
    isViewingVersion,
    dispatch,
    handleSaveWorkflow,
    setVersionParam,
  })

  const canRestoreCurrentVersion = isViewingVersion && viewedVersionDate != null && viewingVersion !== null
  const openRestoreDialogForCurrentVersion = canRestoreCurrentVersion
    ? () => {
        if (versionPermissions.canRestoreSelectedVersion)
          restoreDialog.open({ version: viewingVersion, dateTime: viewedVersionDate })
      }
    : undefined

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
    canRestoreSelectedVersion: versionPermissions.canRestoreSelectedVersion,
    restoreTooltip: versionPermissions.restoreTooltip,
    selectedVersionPermissionError: versionPermissions.selectedVersionPermissionError,
    selectedVersionPermissionLoading: versionPermissions.selectedVersionPermissionLoading,
    retrySelectedVersionPermissions: versionPermissions.retrySelectedVersionPermissions,

    versionSidePanel: buildVersionSidePanel({
      workflowId,
      isNew,
      versionHistoryOpen,
      dispatch,
      filteredVersions,
      publishedVersionName,
      selectedVersion: viewingVersion,
      statusFilter,
      setStatusFilter,
      paginationFooterProps,
      onSelectVersion: versionNavigation.onSelectVersion,
      onExportVersion: exportVersion,
      onOpenInNewWindow: openInNewWindow,
      onViewRunHistory: handleViewRunHistory,
      executedVersionNumbers,
      restoreDialog,
      restoreDialogTitle,
      restoreMutationIsPending: restoreMutation.isPending,
      canConfirmRestore: versionPermissions.canConfirmRestore,
      restorePermissionCheckError: versionPermissions.restorePermissionCheckError,
      restorePermissionCheckLoading: versionPermissions.restorePermissionCheckLoading,
      restoreBlockedStepTypes: versionPermissions.restoreBlockedStepTypes,
      retryRestorePermissions: versionPermissions.retryRestorePermissions,
      handleConfirmRestore,
      versionPublishDialog,
      canPublishSelectedVersion: versionPermissions.canPublishSelectedVersion,
      publishPermissionCheckError: versionPermissions.publishPermissionCheckError,
      publishPermissionCheckLoading: versionPermissions.publishPermissionCheckLoading,
      publishBlockedStepTypes: versionPermissions.publishBlockedStepTypes,
      publishTargetTooltip: versionPermissions.publishTargetTooltip,
      retryPublishPermissions: versionPermissions.retryPublishPermissions,
      publishVersion,
      saveBeforeViewDialog: versionNavigation.saveBeforeViewDialog,
      editVersionDialog,
      canEditSelectedVersion: versionPermissions.canEditSelectedVersion,
      editVersionTooltip: versionPermissions.editVersionTooltip ?? '',
      editPermissionCheckError: versionPermissions.editPermissionCheckError,
      retryEditPermissions: versionPermissions.retryEditPermissions,
      isSavingVersionMetadata: updateMetadataMutation.isPending,
      handleEditVersionSave,
      canCreate,
      canEdit,
      onDuplicateVersion,
    }),
  }
}

export type UseBuilderVersionPanelReturn = ReturnType<typeof useBuilderVersionPanel>
export type VersionSidePanelState = UseBuilderVersionPanelReturn['versionSidePanel']
