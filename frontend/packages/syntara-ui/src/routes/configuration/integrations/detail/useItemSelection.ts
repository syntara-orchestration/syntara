import { useMemo, useState } from 'react'

type SelectableItem = {
  id: string
  enabled?: boolean
}

export function useItemSelection<T extends SelectableItem>(allItems: T[], filteredItems: T[]) {
  const serverEnabledIds = useMemo(() => new Set(allItems.filter((t) => t.enabled).map((t) => t.id)), [allItems])
  const serverKey = useMemo(
    () => [...serverEnabledIds].sort((a, b) => a.localeCompare(b)).join(','),
    [serverEnabledIds]
  )

  const [localState, setLocalState] = useState<{ key: string; ids: Set<string> }>({
    key: serverKey,
    ids: new Set(serverEnabledIds),
  })

  const enabledIds = localState.key === serverKey ? localState.ids : serverEnabledIds

  // Sync local state when server data changes (React-approved setState-during-render pattern)
  if (localState.key !== serverKey) {
    setLocalState({ key: serverKey, ids: new Set(serverEnabledIds) })
  }

  const enabledCount = allItems.filter((t) => enabledIds.has(t.id)).length
  const allSelected = filteredItems.length > 0 && filteredItems.every((t) => enabledIds.has(t.id))

  const isDirty = useMemo(() => {
    if (serverEnabledIds.size !== enabledIds.size) return true
    for (const id of enabledIds) {
      if (!serverEnabledIds.has(id)) return true
    }
    return false
  }, [serverEnabledIds, enabledIds])

  function handleSelectAll(checked: boolean) {
    setLocalState((prev) => {
      const updated = new Set(prev.ids)
      for (const item of filteredItems) {
        if (checked) updated.add(item.id)
        else updated.delete(item.id)
      }
      return { key: prev.key, ids: updated }
    })
  }

  function handleSelectItem(itemId: string, checked: boolean) {
    setLocalState((prev) => {
      const updated = new Set(prev.ids)
      if (checked) updated.add(itemId)
      else updated.delete(itemId)
      return { key: prev.key, ids: updated }
    })
  }

  function resetToServer() {
    setLocalState({ key: serverKey, ids: new Set(serverEnabledIds) })
  }

  return {
    enabledIds,
    enabledCount,
    allSelected,
    isDirty,
    handleSelectAll,
    handleSelectItem,
    resetToServer,
  }
}
