import type { WorkflowAPI } from '@syntara/contracts'
import { useCallback, useState, type Dispatch } from 'react'

import { useDialogState } from '../../../hooks/useDialogState'
import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { detachPromise } from '../../../utils/detachPromise'
import type { BuilderAction } from '../builderReducer'

import { useBuilderVersionHistory } from './useBuilderVersionHistory'

type WorkflowWithVersion = WorkflowAPI.components['schemas']['WorkflowReadWithVersion']
type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']
type PublishVersionAction = (
  version: number,
  publishName?: string,
  changeDescription?: string,
  onSettled?: () => void
) => void

type PublishSelectedVersionArgs = {
  version: number | null
  publish: PublishVersionAction
  closeDialog: () => void
  publishName?: string
  description?: string
}

function closeVersionPublishDialog(cancelWarning: () => void, closeDialog: () => void): void {
  cancelWarning()
  closeDialog()
}

function publishSelectedVersion({
  version,
  publish,
  closeDialog,
  publishName,
  description,
}: PublishSelectedVersionArgs): void {
  if (version != null) publish(version, publishName, description, closeDialog)
}

function openVersionRunHistory(args: {
  isViewingVersion: boolean
  handleExitVersionView: () => void
  dispatch: Dispatch<BuilderAction>
  onOpenRunHistory: (versionNumber: number) => void
  versionNumber: number
}): void {
  if (args.isViewingVersion) args.handleExitVersionView()
  else args.dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: false })
  args.onOpenRunHistory(args.versionNumber)
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
    isPublishingVersion,
    breakingChanges,
    publishReview,
    confirmPublishVersion,
    cancelBreakingChangeWarning,
    isViewingVersion,
    viewedVersionDate,
    viewedVersionStatus,
    viewedVersionDescription,
    viewedVersionName,
    viewedVersionPublishedAt,
    viewedVersionUnpublishedAt,
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

  const handleEditVersionSave = useCallback(
    (publishName: string | null, changeDescription: string | null) => {
      if (!editVersionDialog.item) return
      updateVersionMetadata(editVersionDialog.item.version, publishName, changeDescription)
      editVersionDialog.close()
    },
    [editVersionDialog, updateVersionMetadata]
  )

  const handleViewRunHistory = useCallback(
    (versionNumber: number) =>
      openVersionRunHistory({ isViewingVersion, handleExitVersionView, dispatch, onOpenRunHistory, versionNumber }),
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

  const [pendingViewVersion, setPendingViewVersion] = useState<number | null>(null)
  const handleSelectVersion = useCallback(
    (version: number) => {
      if (isDirty && !isViewingVersion) {
        setPendingViewVersion(version)
      } else {
        dispatch({ type: 'SET_VIEWING_VERSION', payload: version })
        setVersionParam(version)
      }
    },
    [isDirty, isViewingVersion, dispatch, setVersionParam]
  )

  const canRestoreCurrentVersion = isViewingVersion && viewedVersionDate != null && viewingVersion !== null
  const openRestoreDialogForCurrentVersion = canRestoreCurrentVersion
    ? () => restoreDialog.open({ version: viewingVersion, dateTime: viewedVersionDate })
    : undefined

  const handleSaveBeforeView = useCallback(async (): Promise<boolean> => {
    const versionToView = pendingViewVersion
    const saved = await handleSaveWorkflow()
    setPendingViewVersion(null)
    if (saved && versionToView !== null) {
      dispatch({ type: 'SET_VIEWING_VERSION', payload: versionToView })
      setVersionParam(versionToView)
    }
    return saved
  }, [pendingViewVersion, handleSaveWorkflow, dispatch, setVersionParam])

  const handleViewWithoutSaving = useCallback(() => {
    if (pendingViewVersion !== null) {
      dispatch({ type: 'SET_VIEWING_VERSION', payload: pendingViewVersion })
      setVersionParam(pendingViewVersion)
    }
    setPendingViewVersion(null)
  }, [pendingViewVersion, dispatch, setVersionParam])

  const handleCancelSaveBeforeView = useCallback(() => {
    setPendingViewVersion(null)
  }, [])

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

    versionSidePanel: {
      show: !isNew && !!workflowId && versionHistoryOpen,
      filteredVersions,
      publishedVersionName,
      selectedVersion: viewingVersion,
      statusFilter,
      onStatusFilterChange: setStatusFilter,
      paginationFooterProps,
      onClose: () => dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: false }),
      onSelectVersion: handleSelectVersion,
      onRestoreVersion: (v: number, createdAt: string) => restoreDialog.open({ version: v, dateTime: createdAt }),
      onExportVersion: (v: number) => exportVersion(v),
      onOpenInNewWindow: openInNewWindow,
      onPublishVersion: (v: number) => versionPublishDialog.open(v),
      onViewRunHistory: handleViewRunHistory,
      executedVersionNumbers,
      onEditVersion: (v: WorkflowVersion) => editVersionDialog.open(v),
      onDuplicateVersion,

      publishDialog: {
        isOpen: versionPublishDialog.isOpen,
        isPublishing: isPublishingVersion,
        breakingChanges,
        ...publishReview,
        onClose: () => closeVersionPublishDialog(cancelBreakingChangeWarning, versionPublishDialog.close),
        onConfirmContractChanges: confirmPublishVersion,
        onCancelBreakingChanges: cancelBreakingChangeWarning,
        onPublish: (publishName?: string, description?: string) =>
          publishSelectedVersion({
            version: versionPublishDialog.item,
            publish: publishVersion,
            closeDialog: versionPublishDialog.close,
            publishName,
            description,
          }),
      },

      saveBeforeViewDialog: {
        isOpen: pendingViewVersion !== null,
        onSave: handleSaveBeforeView,
        onViewWithoutSaving: handleViewWithoutSaving,
        onCancel: handleCancelSaveBeforeView,
      },

      restoreDialog: {
        isOpen: restoreDialog.isOpen,
        title: restoreDialogTitle,
        isLoading: restoreMutation.isPending,
        onClose: restoreDialog.close,
        onConfirm: handleConfirmRestore,
      },

      editDialog: {
        isOpen: editVersionDialog.isOpen,
        isSaving: updateMetadataMutation.isPending,
        onClose: editVersionDialog.close,
        onSave: handleEditVersionSave,
        initialName: editVersionDialog.item?.name,
        initialDescription: editVersionDialog.item?.change_description,
      },
    },
  }
}

export type UseBuilderVersionPanelReturn = ReturnType<typeof useBuilderVersionPanel>
export type VersionSidePanelState = UseBuilderVersionPanelReturn['versionSidePanel']
