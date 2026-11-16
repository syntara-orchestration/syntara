import type { IntegrationsAPI } from '@syntara/contracts'
import { useMemo, useState } from 'react'

type LLMModelRead = IntegrationsAPI.components['schemas']['LLMModelRead']

/**
 * Tracks the default-model selection for an integration's model list.
 *
 * Uses the React-approved setState-during-render pattern (not useEffect)
 * to stay in sync with the server-derived default when `models` change.
 */
export function useModelDefaultTracking(
  models: LLMModelRead[],
  enabledModelIds: Set<string>,
  onSelectModel: (modelId: string, checked: boolean) => void
) {
  const serverDefaultId = useMemo(() => models.find((m) => m.is_default)?.id ?? null, [models])
  const serverDefaultKey = serverDefaultId ?? ''

  const [localDefault, setLocalDefault] = useState<{ key: string; id: string | null }>({
    key: serverDefaultKey,
    id: serverDefaultId,
  })

  // Sync local state when server data changes (React-approved setState-during-render pattern)
  if (localDefault.key !== serverDefaultKey) {
    setLocalDefault({ key: serverDefaultKey, id: serverDefaultId })
  }

  const defaultModelId = localDefault.id

  const isDefaultDirty = defaultModelId !== serverDefaultId

  const handleSetDefault = (modelId: string) => {
    if (!enabledModelIds.has(modelId)) return
    setLocalDefault((prev) => ({ ...prev, id: modelId }))
  }

  const handleRemoveDefault = () => {
    setLocalDefault((prev) => ({ ...prev, id: null }))
  }

  const handleSelectWithDefaultClear = (modelId: string, checked: boolean) => {
    onSelectModel(modelId, checked)
    if (!checked && modelId === defaultModelId) {
      handleRemoveDefault()
    }
  }

  const resetDefault = () => {
    setLocalDefault({ key: serverDefaultKey, id: serverDefaultId })
  }

  return {
    defaultModelId,
    serverDefaultId,
    isDefaultDirty,
    handleSetDefault,
    handleRemoveDefault,
    handleSelectWithDefaultClear,
    resetDefault,
  }
}
