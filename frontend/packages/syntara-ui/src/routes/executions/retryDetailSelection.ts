import { parseCompositeKey } from '../workflows/execution/utils/activityState'

type RetryDetailSelectionInput = Readonly<{
  retryPanelOpen: boolean
  selectedStepId: string | null
  selectedStepName: string | null
  firstRetryPointId: string | undefined
  activityNameMap: ReadonlyMap<string, string>
}>

export type RetryDetailSelection = Readonly<{
  nodeId: string | null
  nodeName: string | null
}>

/** Keep Run details tied to the selected step, using the retry origin only as the initial fallback. */
export function getRetryDetailSelection({
  retryPanelOpen,
  selectedStepId,
  selectedStepName,
  firstRetryPointId,
  activityNameMap,
}: RetryDetailSelectionInput): RetryDetailSelection {
  const nodeId = retryPanelOpen ? (selectedStepId ?? firstRetryPointId ?? null) : selectedStepId
  const baseId = nodeId ? parseCompositeKey(nodeId).baseId : null
  const mappedName = baseId ? activityNameMap.get(baseId) : undefined

  return {
    nodeId,
    nodeName: selectedStepName ?? (retryPanelOpen && baseId ? (mappedName ?? baseId) : null),
  }
}
