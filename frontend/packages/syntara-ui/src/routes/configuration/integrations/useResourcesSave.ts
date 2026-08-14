import type { Tool } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'

import { integrationsClient } from '../../../client'
import { useDirtyFormGuard } from '../../../hooks/useDirtyFormGuard'
import { useAlerts } from '../../../providers/alerts'
import { getErrorMessage } from '../../../utils/apiErrors'
import { detachPromise } from '../../../utils/detachPromise'

export function useResourcesSave(opts: {
  integrationId: string
  tools: Tool[]
  enabledToolIds: Set<string>
  isDirty: boolean
  resetToServer: () => void
  isActive: boolean
}) {
  const { integrationId, tools, enabledToolIds, isDirty, resetToServer, isActive } = opts
  const { showAlert } = useAlerts()
  const queryClient = useQueryClient()
  const { mutateAsync: updateTools } = integrationsClient.useMutation(
    'patch',
    '/integrations/{integration_id}/tools/bulk_update'
  )
  const [isSaving, setIsSaving] = useState(false)

  const handleSaveRef = useRef<() => Promise<boolean>>(null)

  handleSaveRef.current = async () => {
    const toEnable = tools.filter((t) => enabledToolIds.has(t.id)).map((t) => t.id)
    const toDisable = tools.filter((t) => !enabledToolIds.has(t.id)).map((t) => t.id)
    setIsSaving(true)
    try {
      if (toEnable.length > 0)
        await updateTools({
          params: { path: { integration_id: integrationId } },
          body: { tool_ids: toEnable, enabled: true },
        })
      if (toDisable.length > 0)
        await updateTools({
          params: { path: { integration_id: integrationId } },
          body: { tool_ids: toDisable, enabled: false },
        })
      await queryClient.invalidateQueries({ queryKey: ['all-integration-tools', integrationId] })
      await queryClient.invalidateQueries({ queryKey: ['get', '/integrations/{integration_id}'] })
      showAlert({
        title: 'Changes saved',
        description: 'Resource selections have been updated.',
        variant: 'success',
        autoDismiss: true,
      })
      return true
    } catch (error: unknown) {
      showAlert({
        title: 'Save failed',
        description: `Failed to save changes: ${getErrorMessage(error)}`,
        variant: 'danger',
        autoDismiss: true,
      })
      return false
    } finally {
      setIsSaving(false)
    }
  }

  const handleSave = useCallback(() => {
    detachPromise(handleSaveRef.current?.() ?? Promise.resolve(false))
  }, [])

  useDirtyFormGuard({
    isDirty,
    onSave: () => handleSaveRef.current?.() ?? Promise.resolve(false),
    onDiscard: resetToServer,
    title: 'Save resource changes?',
    body: 'You have unsaved changes to enabled resources. Would you like to save before leaving?',
    saveLabel: 'Save changes',
    isActive,
  })

  return { isSaving, handleSave }
}
