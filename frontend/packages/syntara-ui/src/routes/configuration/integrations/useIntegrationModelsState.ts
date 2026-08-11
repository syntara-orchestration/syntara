import { useCallback, useEffect, useRef } from 'react'

import { useDirtyFormGuard } from '../../../hooks/useDirtyFormGuard'
import { detachPromise } from '../../../utils/detachPromise'

import { useAllIntegrationModels } from './useAllIntegrationModels'
import { useItemSelection } from './useItemSelection'
import { useModelDefaultTracking } from './useModelDefaultTracking'
import { useModelSave } from './useModelSave'

export function useIntegrationModelsState(integrationId: string, isActive: boolean) {
  const { models, isLoading, error, refetch: refetchModels } = useAllIntegrationModels(integrationId)

  const {
    enabledIds: enabledModelIds,
    enabledCount,
    allSelected,
    isDirty: selectionDirty,
    handleSelectAll,
    handleSelectItem: handleSelectModel,
    resetToServer: resetSelectionToServer,
  } = useItemSelection(models, models)

  const {
    defaultModelId,
    serverDefaultId,
    isDefaultDirty,
    handleSetDefault,
    handleRemoveDefault,
    handleSelectWithDefaultClear,
    resetDefault,
  } = useModelDefaultTracking(models, enabledModelIds, handleSelectModel)

  const { save: saveModels, isSaving } = useModelSave(integrationId)

  const isDirty = selectionDirty || isDefaultDirty

  const saveRef = useRef<() => Promise<boolean>>(null)

  useEffect(() => {
    saveRef.current = () => saveModels({ models, enabledModelIds, defaultModelId, serverDefaultId, isDefaultDirty })
  })

  const handleSave = useCallback(() => {
    detachPromise(saveRef.current?.() ?? Promise.resolve(false))
  }, [])

  useDirtyFormGuard({
    isDirty,
    onSave: () => saveRef.current?.() ?? Promise.resolve(false),
    onDiscard: () => {
      resetSelectionToServer()
      resetDefault()
    },
    title: 'Save model changes?',
    body: 'You have unsaved changes to enabled models. Would you like to save before leaving?',
    saveLabel: 'Save model changes',
    isActive,
  })

  return {
    models,
    isLoading,
    error,
    refetchModels,
    enabledModelIds,
    enabledCount,
    allSelected,
    isDirty,
    isSaving,
    handleSave,
    handleSelectAll,
    defaultModelId,
    handleSelectWithDefaultClear,
    handleSetDefault,
    handleRemoveDefault,
    resetSelectionToServer,
    resetDefault,
  }
}
