import type { IntegrationsAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'

import { integrationsClient } from '../../../client'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'

type LLMModelRead = IntegrationsAPI.components['schemas']['LLMModelRead']
type BulkUpdateResponse = IntegrationsAPI.components['schemas']['LLMModelBulkUpdateResponse']

export type SaveParams = {
  models: LLMModelRead[]
  enabledModelIds: Set<string>
  defaultModelId: string | null
  serverDefaultId: string | null
  isDefaultDirty: boolean
}

const BULK_UPDATE_BATCH_SIZE = 1000

type BulkUpdateArgs = {
  params: { path: { integration_id: string } }
  body: { model_ids: string[]; enabled: boolean }
}

export async function chunkedBulkUpdate(
  bulkUpdateFn: (args: BulkUpdateArgs) => Promise<BulkUpdateResponse>,
  integrationId: string,
  modelIds: string[],
  enabled: boolean
): Promise<{ updated_count: number; skipped_count: number }> {
  let totalUpdated = 0
  let totalSkipped = 0
  for (let i = 0; i < modelIds.length; i += BULK_UPDATE_BATCH_SIZE) {
    const batch = modelIds.slice(i, i + BULK_UPDATE_BATCH_SIZE)
    const result = await bulkUpdateFn({
      params: { path: { integration_id: integrationId } },
      body: { model_ids: batch, enabled },
    })
    totalUpdated += result.updated_count
    totalSkipped += result.skipped_count
  }
  return { updated_count: totalUpdated, skipped_count: totalSkipped }
}

async function invalidateModelQueries(queryClient: ReturnType<typeof useQueryClient>, integrationId: string) {
  await queryClient.invalidateQueries({ queryKey: ['all-integration-models', integrationId] })
  await queryClient.invalidateQueries({ queryKey: ['get', '/integrations/{integration_id}'] })
}

/**
 * Encapsulates bulk model enable/disable and default-model updates for a single integration.
 *
 * Uses a ref-based save function to avoid stale closures when called from unsaved-changes guards.
 * On partial failure (e.g. bulk update succeeds but default update fails), queries are invalidated
 * immediately so the UI refreshes to match server state.
 */
export function useModelSave(integrationId: string) {
  const { showAlert } = useAlerts()
  const queryClient = useQueryClient()
  const [isSaving, setIsSaving] = useState(false)

  const { mutateAsync: bulkUpdateModels } = integrationsClient.useMutation(
    'patch',
    '/integrations/{integration_id}/models/bulk_update'
  )
  const { mutateAsync: updateModel } = integrationsClient.useMutation(
    'patch',
    '/integrations/{integration_id}/models/{model_id}'
  )

  const saveRef = useRef<(params: SaveParams) => Promise<boolean>>(() => Promise.resolve(false))

  // eslint-disable-next-line react-hooks/refs -- expose latest save closure to parent via stable ref
  saveRef.current = async (params: SaveParams): Promise<boolean> => {
    const { models, enabledModelIds, defaultModelId, serverDefaultId, isDefaultDirty } = params
    setIsSaving(true)
    try {
      const toEnable = models.filter((m) => enabledModelIds.has(m.id)).map((m) => m.id)
      const toDisable = models.filter((m) => !enabledModelIds.has(m.id)).map((m) => m.id)

      if (toEnable.length > 0) await chunkedBulkUpdate(bulkUpdateModels, integrationId, toEnable, true)
      if (toDisable.length > 0) await chunkedBulkUpdate(bulkUpdateModels, integrationId, toDisable, false)

      if (isDefaultDirty && defaultModelId)
        await updateModel({
          params: { path: { integration_id: integrationId, model_id: defaultModelId } },
          body: { is_default: true },
        })
      else if (isDefaultDirty && !defaultModelId && serverDefaultId)
        await updateModel({
          params: { path: { integration_id: integrationId, model_id: serverDefaultId } },
          body: { is_default: false },
        })

      await invalidateModelQueries(queryClient, integrationId)
      showAlert({
        title: 'Models updated',
        description: 'Enabled models and default selection have been updated.',
        variant: 'success',
        autoDismiss: true,
      })
      return true
    } catch (error: unknown) {
      // Invalidate on partial failure — UI must reflect server state
      await invalidateModelQueries(queryClient, integrationId)
      showAlert({
        title: 'Failed to update models',
        description: getErrorMessage(error),
        variant: 'danger',
        autoDismiss: true,
      })
      return false
    } finally {
      setIsSaving(false)
    }
  }

  const save = useCallback((params: SaveParams) => saveRef.current(params), [])

  return { save, isSaving }
}
