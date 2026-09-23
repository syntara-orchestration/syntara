import { useCallback, useMemo, useState } from 'react'

import type { ActivityState } from '../../workflows/execution/types'
import { parseCompositeKey } from '../../workflows/execution/utils/activityState'
import type { ActivityOrderItem } from '../ExecutionActivityTable'
import { resolveNodeName } from '../useActivityNameMap'

type UseSelectedActivityOptions = {
  selectedNodeId: string | null | undefined
  selectedNodeNameProp: string | null | undefined
  activityStates: Map<string, ActivityState>
  activityOrder: ActivityOrderItem[]
  nameMap: Map<string, string>
  onNodeSelect?: (nodeId: string, nodeName: string) => void
}

export function useSelectedActivity(opts: UseSelectedActivityOptions) {
  const { selectedNodeId, selectedNodeNameProp, activityStates, activityOrder, nameMap, onNodeSelect } = opts
  const [selectedActivityKey, setSelectedActivityKey] = useState<string | null>(null)
  const [prevNodeId, setPrevNodeId] = useState(selectedNodeId)

  const resolvedNodeId = useMemo(() => {
    if (selectedNodeId != null) return selectedNodeId
    if (selectedActivityKey) {
      return parseCompositeKey(selectedActivityKey).baseId
    }
    return null
  }, [selectedNodeId, selectedActivityKey])

  if (selectedNodeId !== prevNodeId) {
    setPrevNodeId(selectedNodeId)
    if (selectedActivityKey !== null) {
      setSelectedActivityKey(null)
    }
  }

  const effectiveKey = useMemo(() => {
    if (selectedActivityKey) {
      if (selectedNodeId) {
        const { baseId } = parseCompositeKey(selectedActivityKey)
        if (baseId === selectedNodeId) return selectedActivityKey
      } else {
        return selectedActivityKey
      }
    }
    return selectedNodeId ?? null
  }, [selectedActivityKey, selectedNodeId])

  const matchedActivity = useMemo(() => activityOrder.find((a) => a.id === effectiveKey), [activityOrder, effectiveKey])
  const displayNodeName =
    selectedNodeNameProp ?? matchedActivity?.name ?? resolveNodeName(nameMap, effectiveKey) ?? null
  const selectedNodeState = effectiveKey ? activityStates.get(effectiveKey) : undefined
  const selectedNodeType = matchedActivity?.type

  const handleRowClick = useCallback(
    (activityKey: string, nodeName: string) => {
      setSelectedActivityKey(activityKey)
      const { baseId } = parseCompositeKey(activityKey)
      onNodeSelect?.(baseId, nodeName)
    },
    [onNodeSelect]
  )

  return { resolvedNodeId, effectiveKey, displayNodeName, selectedNodeState, selectedNodeType, handleRowClick }
}
