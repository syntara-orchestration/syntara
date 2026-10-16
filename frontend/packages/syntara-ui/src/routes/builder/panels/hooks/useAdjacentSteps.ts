import { useStore } from '@xyflow/react'
import { useMemo } from 'react'

import { getAdjacentStepsFromFlow } from './getAdjacentStepsFromFlow'

export type { AdjacentSteps } from './getAdjacentStepsFromFlow'

/**
 * Returns the immediate upstream and downstream neighbors of `nodeId`
 * based on the live React Flow canvas graph (display IDs, same as Run/test-step).
 */
export function useAdjacentSteps(nodeId: string | undefined) {
  const edges = useStore((state) => state.edges)
  const nodes = useStore((state) => state.nodes)

  return useMemo(() => {
    if (!nodeId) {
      return { upstream: [], downstream: [] }
    }

    return getAdjacentStepsFromFlow(nodeId, edges, nodes)
  }, [nodeId, edges, nodes])
}
