import type { ExecutionPlaneAPI } from '@syntara/contracts'

type Placement = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']['placement']

/** Node selectors from kubernetes placement; empty for non-kubernetes targets. */
export function getNodeSelectors(placement: Placement | undefined): readonly string[] {
  if (placement?.type === 'kubernetes') {
    return placement.node_selectors ?? []
  }
  return []
}
